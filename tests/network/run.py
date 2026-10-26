#!/usr/bin/env python3
"""Real pasta/TLS regression. Requires Podman >=5.3, pasta and openssl.

Uses the existing runtime image and an isolated HTTPS fixture on a random
port. Does not contact an IdP or change the host's DNS/firewall/trust store.
"""
import http.server
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'imageroot/pypkg'))
import vaultwarden_network as network

IMAGE = os.environ.get('VW_RUNTIME_IMAGE', 'localhost/vaultwarden-reworked-server:0.1.0-rc.1')


def command(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout.strip()


class PastaTLS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='vw-pasta-')
        cls.addClassCleanup(cls.directory.cleanup)
        path = Path(cls.directory.name)
        cls.ca = path / 'cert.pem'
        key = path / 'key.pem'
        command('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
            '-keyout', str(key), '-out', str(cls.ca), '-days', '1',
            '-subj', '/CN=sso.pasta.test', '-addext', 'subjectAltName=DNS:sso.pasta.test')
        cls.ca.chmod(0o644)

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                payload = json.dumps({'issuer': cls.issuer}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        cls.server = http.server.ThreadingHTTPServer(('0.0.0.0', 0), Handler)
        cls.addClassCleanup(cls.server.server_close)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cls.ca, key)
        cls.server.socket = ctx.wrap_socket(cls.server.socket, server_side=True)
        cls.issuer = f'https://sso.pasta.test:{cls.server.server_port}/realms/ad.test'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.addClassCleanup(cls.server.shutdown)
        route = json.loads(command('ip', '-j', 'route', 'get', '192.0.2.1'))[0]
        cls.public_ip = route['prefsrc']

    def setUp(self):
        self.name = 'vw-pasta-test-' + uuid.uuid4().hex[:12]
        self.addCleanup(subprocess.run, ['podman', 'rm', '-f', self.name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start(self, options, trust=True):
        args = ['podman', 'run', '-d', '--name', self.name, '--network=pasta'] + options
        if trust:
            args += ['--volume', f'{self.ca}:/etc/ssl/certs/ca-certificates.crt:ro,Z']
        args += ['--entrypoint=/bin/sleep', IMAGE, '300']
        command(*args)

    def test_01_public_host_address_fails_without_fix(self):
        self.start(['--add-host=sso.pasta.test:' + self.public_ip])
        with self.assertRaisesRegex(ValueError, 'OIDC discovery failed'):
            network.check_discovery(self.issuer, timeout=0, container=self.name)

    def test_02_gateway_survives_restart_and_recreation(self):
        options = network.network_options({'domain': 'ad.test'}, self.issuer, '2', '2', 'pasta')
        self.start(options)
        network.check_discovery(self.issuer, timeout=0, container=self.name)
        command('podman', 'restart', self.name)
        network.check_discovery(self.issuer, timeout=0, container=self.name)
        command('podman', 'rm', '-f', self.name)
        self.start(options)
        network.check_discovery(self.issuer, timeout=0, container=self.name)

    def test_03_gateway_does_not_bypass_tls_trust(self):
        self.start(['--add-host=sso.pasta.test:host-gateway'], trust=False)
        result = subprocess.run(['podman', 'exec', self.name, 'curl', '--silent',
            '--show-error', '--connect-timeout', '3', '--max-time', '8',
            self.issuer + '/.well-known/openid-configuration'], capture_output=True)
        self.assertEqual(result.returncode, 60, result.stderr.decode())
        with self.assertRaisesRegex(ValueError, 'OIDC discovery failed'):
            network.check_discovery(self.issuer, timeout=0, container=self.name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
