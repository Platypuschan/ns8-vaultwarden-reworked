"""Small supported NS8 task API fixture. Never logs authorization headers."""
import base64
import http.server
import json
import secrets
import threading
import time

class CoreFixture:
    def __init__(self):
        self.owners = {'owner1', 'owner2'}
        self.tokens = {}
        self.requests = 0
        self.available = True
        fixture = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def send(self, code, result):
                data = json.dumps(result).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def permitted(self):
                fixture.requests += 1
                token = self.headers.get('Authorization', '').removeprefix('Bearer ')
                return fixture.available and fixture.tokens.get(token) in fixture.owners
            def do_POST(self):
                length = int(self.headers.get('Content-Length', '0'))
                body = json.loads(self.rfile.read(length))
                if not self.permitted():
                    return self.send(403, {})
                if self.path != '/api/cluster/tasks' or body.get('action') != 'list-users':
                    return self.send(404, {})
                self.send(201, {'data': {'id': 'fixture-task'}})
            def do_GET(self):
                if not self.permitted():
                    return self.send(403, {})
                self.send(200, {'data': {'exit_code': 0, 'output': [{'user': user} for user in fixture.owners]}})
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
    def token(self, user):
        payload = base64.urlsafe_b64encode(json.dumps({'id': user, 'exp': int(time.time()) + 3600}).encode()).decode().rstrip('=')
        token = 'eyJhbGciOiJIUzI1NiJ9.' + payload + '.' + secrets.token_urlsafe(32)
        self.tokens[token] = user
        return token
    def close(self):
        self.server.shutdown()
        self.server.server_close()
