#!/usr/bin/env python3
"""Browser fixture: NS8 task bridge contract plus the real Vaultwarden runtime.

Actual NS8 owner/reader authorization is separately tested by ns8_access.py.
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
from core_fixture import CoreFixture

ROOT = Path(__file__).resolve().parents[2]
image = os.environ.get('VW_RUNTIME_IMAGE', 'localhost/vaultwarden-reworked-server:admin-ui')
name = 'vw-admin-browser-' + secrets.token_hex(5)
token = secrets.token_urlsafe(48)
core_fixture = CoreFixture()
import atexit
atexit.register(core_fixture.close)
core_fixture.owners.update(('tab', 'public-suffix'))
owner_tokens = {role: core_fixture.token(role) for role in ('owner1', 'owner2', 'tab', 'public-suffix')}


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
            role = self.path.split('role=', 1)[-1]
            body = '''<!doctype html><script>
            location.hash='#/apps/vaultwarden-reworked1/settings';
            localStorage.setItem('loginInfo', JSON.stringify({token:'JWT'}));
            const events=new Map();
            const root={$once:(name,fn)=>events.set(name,fn),$off:(name)=>events.delete(name)};
            window.core={$root:root,$children:[{createModuleTaskForApp:async (module,request)=>{
              const response=await fetch('/test-task?role=ROLE',{method:'POST'});
              const event=`open-admin-${response.ok?'completed':'aborted'}-${request.extra.eventId}`;
              const fn=events.get(event); if(fn) fn(null,{output:response.ok?await response.json():null});
            }}]};</script><iframe src="/cluster-admin/apps/vaultwarden-reworked1/index.html"></iframe>'''.replace('ROLE', role).replace('JWT', owner_tokens.get(role, 'reader'))
            self.send(200, body.encode())
        elif self.path.startswith('/cluster-admin/apps/') and self.path.endswith('/index.html'):
            self.send(200, (ROOT / 'ui/index.html').read_bytes())
        elif self.path.startswith('/cluster-admin/apps/') and self.path.endswith('/admin.js'):
            self.send(200, (ROOT / 'ui/admin.js').read_bytes(), 'application/javascript')
        else:
            self.proxy()

    def do_POST(self):
        if self.path.startswith('/test-task?'):
            if self.path.endswith('role=reader'):
                self.send(403, b'{}', 'application/json')
            else:
                # role=tab: an installation whose cluster manager may not embed the page
                ancestors = [] if self.path.endswith('role=tab') else [base, suffix_cluster]
                destination = suffix_vault if self.path.endswith('role=public-suffix') else vault
                self.send(200, json.dumps({'url': destination + '/admin/',
                    'frame_ancestors': ancestors}).encode(), 'application/json')
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
            '-v', f'{path / "data"}:/data:Z', '-e', 'NS8_MANAGED_CONFIG=true', '-e', 'ADMIN_RATELIMIT_MAX_BURST=30',
            '-e', 'SSO_ENABLED=true', '-e', 'SSO_ONLY=true', '-e', 'SSO_AUTHORITY=https://sso.example.test/realms/ad.test',
            '-e', 'SSO_CLIENT_ID=fixture', '-e', 'SSO_CLIENT_SECRET=fixture',
            '-e', 'NS8_CORE_API=' + core_fixture.url, '-e', 'ADMIN_TOKEN=' + token, '-e', 'DOMAIN=' + vault,
            '-e', 'ALLOWED_IFRAME_ANCESTORS=' + base + ' ' + suffix_cluster, image)
        ready()
        subprocess.run(['node', str(ROOT / 'tests/admin/browser.mjs')], check=True,
            env=dict(os.environ, TEST_BASE=base))
    finally:
        subprocess.run(['podman', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        server.shutdown()
        server.server_close()
