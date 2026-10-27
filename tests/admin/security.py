#!/usr/bin/env python3
"""Exercise the NS8 admin session bridge against a real patched runtime."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import requests
from core_fixture import CoreFixture

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'imageroot/pypkg'))
from vaultwarden_revoke import AdminAPI

class AdminBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = CoreFixture()
        cls.directory = tempfile.TemporaryDirectory(prefix='vw-admin-security-')
        cls.worker = secrets.token_urlsafe(48)
        cls.name = 'vw-admin-security-' + secrets.token_hex(4)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        cls.base = f'http://127.0.0.1:{port}'
        cls.origin = 'https://cluster.example.test'
        subprocess.run(['podman', 'run', '-d', '--name', cls.name, '--network=host',
            '-e', 'ROCKET_ADDRESS=127.0.0.1', '-e', f'ROCKET_PORT={port}',
            '-e', 'NS8_MANAGED_CONFIG=true', '-e', 'NS8_CORE_API=' + cls.core.url,
            '-e', 'ADMIN_RATELIMIT_MAX_BURST=30', '-e', 'ADMIN_TOKEN=' + cls.worker, '-e', 'DOMAIN=' + cls.base,
            '-e', 'ALLOWED_IFRAME_ANCESTORS=' + cls.origin,
            '-v', cls.directory.name + ':/data:Z',
            os.environ.get('VW_RUNTIME_IMAGE', 'localhost/vaultwarden-reworked-server:security')],
            check=True, capture_output=True)
        for _ in range(60):
            try:
                if requests.get(cls.base + '/alive', timeout=2).status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(1)
        raise RuntimeError('Runtime did not start')

    @classmethod
    def tearDownClass(cls):
        subprocess.run(['podman', 'rm', '-f', cls.name], capture_output=True)
        cls.core.close()
        cls.directory.cleanup()

    def setUp(self):
        self.core.available = True
        self.core.owners = {'owner1', 'owner2'}

    def login(self, user='owner1', origin=None):
        session = requests.Session()
        response = session.post(self.base + '/admin/',
            data={'token': self.core.token(user)}, headers={'Origin': origin or self.origin}, timeout=15)
        return session, response

    def test_01_anonymous_and_forged_credentials_are_denied(self):
        self.assertEqual(requests.get(self.base + '/admin/users', timeout=10).status_code, 403)
        response = requests.get(self.base + '/admin/users', cookies={'NS8_ADMIN': 'forged'}, timeout=10)
        self.assertEqual(response.status_code, 403)
        reader, response = self.login('reader')
        self.assertEqual(response.status_code, 401)
        self.assertFalse(reader.cookies.get('NS8_ADMIN'))

    def test_02_each_request_checks_current_rights_and_revocation_is_immediate(self):
        session, response = self.login()
        self.assertEqual(response.status_code, 200, response.text[:200])
        self.assertTrue(session.cookies.get('NS8_ADMIN'))
        self.assertFalse(session.cookies.get('VW_ADMIN'))
        before = self.core.requests
        self.assertEqual(session.get(self.base + '/admin/users', timeout=15).status_code, 200)
        self.assertGreater(self.core.requests, before)
        self.core.owners.remove('owner1')
        self.assertEqual(session.get(self.base + '/admin/users', timeout=15).status_code, 403)
        self.core.owners.add('owner1')
        # A revoked bridge session stays invalid, even after regrant.
        self.assertEqual(session.get(self.base + '/admin/users', timeout=15).status_code, 403)

    def test_03_backend_cookie_alone_is_no_bypass(self):
        worker = requests.Session()
        response = worker.post(self.base + '/admin/', data={'token': self.worker},
            headers={'X-NS8-Worker': self.worker}, timeout=15)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(worker.cookies.get('VW_ADMIN'))
        self.assertEqual(worker.get(self.base + '/admin/users', timeout=15).status_code, 403)
        api = AdminAPI(self.base, self.worker, self.directory.name)
        self.assertIsInstance(api.users(), list)

    def test_04_core_failure_denies_existing_session(self):
        session, response = self.login()
        self.assertEqual(response.status_code, 200)
        self.core.available = False
        self.assertEqual(session.get(self.base + '/admin/users', timeout=15).status_code, 403)

    def test_05_logout_destroys_server_session(self):
        session, response = self.login('owner2')
        cookie = session.cookies.get('NS8_ADMIN')
        self.assertTrue(cookie)
        session.get(self.base + '/admin/logout', timeout=15)
        replay = requests.get(self.base + '/admin/users', cookies={'NS8_ADMIN': cookie}, timeout=15)
        self.assertEqual(replay.status_code, 403)

    def test_06_untrusted_login_origin_is_denied(self):
        session, response = self.login(origin='https://attacker.example.test')
        self.assertEqual(response.status_code, 401)
        self.assertFalse(session.cookies.get('NS8_ADMIN'))

if __name__ == '__main__':
    unittest.main(verbosity=2)
