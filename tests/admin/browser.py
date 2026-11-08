#!/usr/bin/env python3
"""Browser fixture: NS8 task bridge contract plus the real Vaultwarden runtime.

The fake open-admin task issues real tickets; actual NS8 owner/reader
authorization is separately tested by ns8_access.py.
"""
import http.client
import http.server
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'imageroot/pypkg'))
from vaultwarden_admin import issue_ticket
import vaultwarden_panel as panel
import vaultwarden_revoke as revoke

image = os.environ.get('VW_RUNTIME_IMAGE', 'localhost/vaultwarden-reworked-server:admin-ui')
name = 'vw-admin-browser-' + secrets.token_hex(5)
token = secrets.token_urlsafe(48)
# Short sessions: the page renews every 5 s, a revoked user drops out quickly
SESSION_SECONDS = 12
tickets = None
revoked = set()
# Results of module actions wait here until the cluster manager page asks
events = []
events_lock = threading.Lock()
STATE_DIR = None
MIME = {'.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png',
    '.svg': 'image/svg+xml', '.html': 'text/html'}


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return result.stdout.strip()


def free_port():
    with socket.socket() as connection:
        connection.bind(('127.0.0.1', 0))
        return connection.getsockname()[1]


port = free_port()
app_port = free_port()
base = f'https://cluster.example.test:{port}'
vault = f'https://vault.example.test:{port}'
suffix_cluster = f'https://cluster.two.co.uk:{port}'
suffix_vault = f'https://vault.one.co.uk:{port}'


def ready():
    for _ in range(60):
        try:
            connection = http.client.HTTPConnection('127.0.0.1', app_port, timeout=2)
            connection.request('GET', '/alive')
            response = connection.getresponse()
            response.read()
            if response.status == 200:
                return
        except OSError:
            pass
        finally:
            connection.close()
        time.sleep(1)
    raise RuntimeError('Browser fixture runtime failed to start')


def open_admin(role):
    """Fake open-admin: real tickets, or the refusal NS8 gives a reader."""
    if role == 'reader' or role in revoked:
        return None
    # role=tab: an installation whose cluster manager may not embed the page
    ancestors = [] if role == 'tab' else [base, suffix_cluster]
    destination = suffix_vault if role == 'public-suffix' else vault
    # owner1: an installation whose revocation timer keeps failing
    revocation = {'state': 'warning' if role == 'owner1' else 'ok'}
    return {'url': destination + '/admin/', 'ticket': issue_ticket(role, tickets),
        'session_seconds': SESSION_SECONDS, 'frame_ancestors': ancestors, 'revocation': revocation}


def run_action(role, action, data):
    """The module actions, with the real panel code on the real runtime."""
    connection = revoke.AdminAPI(f'http://127.0.0.1:{app_port}', token, state_dir=STATE_DIR)
    if action == 'get-name':
        return {'name': 'vaultwarden-reworked1'}
    if action == 'get-configuration':
        return {'host': 'vault.example.test', 'smtp_mode': 'custom', 'smarthost_available': False,
            'revocation': {'state': 'warning' if role == 'owner1' else 'ok'}}
    if action == 'open-admin':
        return open_admin(role)
    if action == 'query-panel-data':
        return {'section': data['section'], 'data': panel.get_data(data['section'], connection)}
    if action == 'set-panel-settings':
        panel.save_settings(data['values'], connection)
        return {'saved': True}
    if action == 'reset-panel-settings':
        panel.reset_settings(connection)
        return {'reset': True}
    if action == 'manage-user':
        panel.manage_user(data['operation'], data.get('user_id'), data.get('role'), data.get('org_id'), connection)
        return {'done': True}
    if action == 'manage-organization':
        panel.delete_organization(data['org_id'], connection)
        return {'done': True}
    if action == 'test-smtp':
        panel.test_smtp(data['email'], connection)
        return {'sent': True}
    raise ValueError('Unknown action ' + action)


def queue_task(role, request):
    action, event_id = request['action'], request['extra']['eventId']
    try:
        output = run_action(role, action, request.get('data') or {})
        event = [f'{action}-completed-{event_id}', [None, {'output': output}]] if output is not None else \
            [f'{action}-aborted-{event_id}', [None, {'action': action}]]
    except (ValueError, revoke.RevokeError) as error:
        message = getattr(error, 'detail', '') or str(error)
        event = [f'{action}-validation-failed-{event_id}', [[{'message': message}]]]
    with events_lock:
        events.append({'name': event[0], 'args': event[1]})


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, data, mime='text/html'):
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, ssl.SSLEOFError):
            pass  # A browser context may close while an asset is in flight.

    def do_GET(self):
        if self.path == '/test-control':
            self.send(200, b'<!doctype html><title>Test control</title>')
        elif self.path.startswith('/cluster-admin/?'):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            role = query.get('role', ['owner1'])[0]
            page = query.get('page', ['admin'])[0]
            body = '''<!doctype html><script>
            location.hash='#/apps/vaultwarden-reworked1?page=PAGE';
            const events=new Map();
            // What the cluster manager offers the module page
            const root={apiUrl:'/test-api/ROLE',$on(){},$emit(){},
              $once:(name,fn)=>events.set(name,fn),$off:(name,fn)=>{if(!fn||events.get(name)===fn) events.delete(name)}};
            window.notifications=[];
            window.core={$root:root,$children:[],
              $route:{path:'/apps/vaultwarden-reworked1',fullPath:'/apps/vaultwarden-reworked1?page=PAGE'},
              $router:{replace(){},push(){}}};
            setInterval(async()=>{
              const answer=await fetch('/test-api/events'); 
              for(const event of await answer.json()){
                const fn=events.get(event.name);
                if(fn){events.delete(event.name); fn(...event.args);}
              }
            },100);</script><iframe style="position:absolute;top:48px;left:256px;width:1000px;height:700px;border:none" src="/cluster-admin/apps/vaultwarden-reworked1/index.html"></iframe>'''.replace('ROLE', role).replace('PAGE', page)
            self.send(200, body.encode())
        elif self.path == '/test-api/events':
            with events_lock:
                pending, events[:] = list(events), []
            self.send(200, json.dumps(pending).encode(), 'application/json')
        elif self.path.startswith('/cluster-admin/css/'):
            self.send(200, b'', 'text/css')
        elif self.path.startswith('/cluster-admin/apps/'):
            name = urllib.parse.urlsplit(self.path).path.split('/', 4)[-1] or 'index.html'
            target = (ROOT / 'ui/dist' / name).resolve()
            if (ROOT / 'ui/dist').resolve() in target.parents and target.is_file():
                self.send(200, target.read_bytes(), MIME.get(target.suffix, 'application/octet-stream'))
            else:
                self.send(404, b'not found')
        else:
            self.proxy()

    def do_POST(self):
        if self.path.startswith('/test-api/') and self.path.endswith('/tasks'):
            role = self.path.split('/')[2]
            length = int(self.headers.get('Content-Length', '0'))
            request = json.loads(self.rfile.read(length) or b'{}')
            queue_task(role, request)
            self.send(200, b'{}', 'application/json')
        elif self.path.startswith('/test-revoke?'):
            revoked.add(self.path.split('role=', 1)[-1])
            self.send(200, b'{}', 'application/json')
        elif self.path == '/test-restart':
            command('podman', 'restart', name)
            ready()
            self.send(200, b'{}', 'application/json')
        else:
            self.proxy()

    def proxy(self):
        length = int(self.headers.get('Content-Length', '0'))
        data = self.rfile.read(length) if length else None
        headers = {key: value for key, value in self.headers.items() if key.lower() not in ('host', 'connection')}
        headers['Host'] = f'vault.example.test:{port}'
        headers['X-Forwarded-Proto'] = 'https'
        connection = http.client.HTTPConnection('127.0.0.1', app_port, timeout=30)
        connection.request(self.command, self.path, body=data, headers=headers)
        response = connection.getresponse()
        content = response.read()
        self.send_response(response.status)
        for key, value in response.getheaders():
            if key.lower() not in ('connection', 'transfer-encoding', 'content-length'):
                self.send_header(key, value)
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)
        connection.close()


with tempfile.TemporaryDirectory(prefix='vw-admin-browser-') as directory:
    path = Path(directory)
    cert, key = path / 'cert.pem', path / 'key.pem'
    command('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(key),
        '-out', str(cert), '-days', '1', '-subj', '/CN=vault.example.test',
        '-addext', 'subjectAltName=DNS:cluster.example.test,DNS:vault.example.test,DNS:cluster.two.co.uk,DNS:vault.one.co.uk')
    (path / 'data').mkdir()
    STATE_DIR = str(path)
    tickets = str(path / 'tickets')
    os.mkdir(tickets, 0o700)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', port), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        # UI fixture only: avoid coupling browser tests to rootless port-forward
        # teardown. The dedicated pasta and NS8 suites cover container networking.
        command('podman', 'run', '-d', '--name', name, '--network=host',
            '-e', 'ROCKET_ADDRESS=127.0.0.1', '-e', f'ROCKET_PORT={app_port}',
            '-v', f'{path / "data"}:/data:Z', '-v', f'{tickets}:/ns8-admin-tickets:Z',
            '-e', 'NS8_MANAGED_CONFIG=true', '-e', f'NS8_ADMIN_SESSION_SECONDS={SESSION_SECONDS}',
            '-e', 'ADMIN_RATELIMIT_MAX_BURST=30',
            '-e', 'SSO_ENABLED=true', '-e', 'SSO_ONLY=true', '-e', 'SSO_AUTHORITY=https://sso.example.test/realms/ad.test',
            '-e', 'SSO_CLIENT_ID=fixture', '-e', 'SSO_CLIENT_SECRET=fixture',
            '-e', 'ADMIN_TOKEN=' + token, '-e', 'DOMAIN=' + vault,
            '-e', 'ALLOWED_IFRAME_ANCESTORS=' + base + ' ' + suffix_cluster, image)
        ready()
        subprocess.run(['node', str(ROOT / 'tests/admin/browser.mjs')], check=True,
            env=dict(os.environ, TEST_BASE=base))
    finally:
        subprocess.run(['podman', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        server.shutdown()
        server.server_close()
