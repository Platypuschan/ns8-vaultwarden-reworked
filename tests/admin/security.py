#!/usr/bin/env python3
"""Exercise the NS8 admin ticket bridge against a real patched runtime."""
import hashlib
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'imageroot/pypkg'))
from vaultwarden_admin import issue_ticket
import vaultwarden_config as policy
from vaultwarden_revoke import AdminAPI

# Short sessions keep the expiry tests fast; NS8 installs use 120 s.
SESSION_SECONDS = 4


class AdminBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='vw-admin-security-')
        cls.tickets = os.path.join(cls.directory.name, 'tickets')
        os.mkdir(cls.tickets, 0o700)
        os.mkdir(os.path.join(cls.directory.name, 'data'))
        cls.worker = secrets.token_urlsafe(48)
        cls.name = 'vw-admin-security-' + secrets.token_hex(4)
        image = os.environ.get('VW_RUNTIME_IMAGE', 'localhost/vaultwarden-reworked-server:security')
        # As in production: the server holds only the Argon2 hash (read from
        # an env file, so `$` stays literal); the worker keeps the clear text.
        cls.env_file = os.path.join(cls.directory.name, 'vaultwarden.env')
        with open(cls.env_file, 'w') as f:
            f.write('ADMIN_TOKEN=' + policy.argon2_hash(cls.worker, image) + '\n')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        cls.base = f'http://127.0.0.1:{port}'
        cls.origin = 'https://cluster.example.test'
        subprocess.run(['podman', 'run', '-d', '--name', cls.name, '--network=host',
            '-e', 'ROCKET_ADDRESS=127.0.0.1', '-e', f'ROCKET_PORT={port}',
            '-e', 'NS8_MANAGED_CONFIG=true', '-e', f'NS8_ADMIN_SESSION_SECONDS={SESSION_SECONDS}',
            '-e', 'ADMIN_RATELIMIT_MAX_BURST=30', '--env-file', cls.env_file, '-e', 'DOMAIN=' + cls.base,
            '-e', 'ALLOWED_IFRAME_ANCESTORS=' + cls.origin,
            '-v', os.path.join(cls.directory.name, 'data') + ':/data:Z',
            '-v', cls.tickets + ':/ns8-admin-tickets:Z',
            image],
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
        # Files renamed by the container belong to the same rootless user
        cls.directory.cleanup()

    def login(self, user='owner1', handle=None, origin=None, ticket=None):
        handle = handle or secrets.token_urlsafe(32)
        ticket = ticket or issue_ticket(user, self.tickets)
        session = requests.Session()
        response = session.post(self.base + '/admin/', data={'token': ticket + ':' + handle},
            headers={'Origin': origin or self.origin}, timeout=15)
        return session, response, handle

    def renew(self, user, handle, origin=None):
        return requests.post(self.base + '/admin/ns8/renew',
            data={'token': issue_ticket(user, self.tickets) + ':' + handle},
            headers={'Origin': origin or self.origin}, timeout=15).status_code

    def users(self, session):
        return session.get(self.base + '/admin/users', timeout=15).status_code

    def test_01_anonymous_and_forged_credentials_are_denied(self):
        self.assertEqual(requests.get(self.base + '/admin/users', timeout=10).status_code, 403)
        response = requests.get(self.base + '/admin/users', cookies={'NS8_ADMIN': 'forged'}, timeout=10)
        self.assertEqual(response.status_code, 403)
        # A guessed ticket, an NS8-style JWT and the worker token are no tickets
        for token in (secrets.token_urlsafe(32) + ':' + secrets.token_urlsafe(32),
                'eyJhbGciOiJIUzI1NiJ9.eyJpZCI6ImFkbWluIn0.' + secrets.token_urlsafe(32), self.worker):
            session = requests.Session()
            response = session.post(self.base + '/admin/', data={'token': token},
                headers={'Origin': self.origin}, timeout=15)
            self.assertEqual(response.status_code, 401)
            self.assertFalse(session.cookies.get('NS8_ADMIN'))

    def test_02_a_ticket_opens_one_session_once(self):
        ticket = issue_ticket('owner1', self.tickets)
        session, response, handle = self.login(ticket=ticket)
        self.assertEqual(response.status_code, 200, response.text[:200])
        self.assertFalse(self.worker in response.text, 'Backend token must not be embedded in admin settings')
        self.assertTrue(session.cookies.get('NS8_ADMIN'))
        self.assertFalse(session.cookies.get('VW_ADMIN'))
        self.assertEqual(self.users(session), 200)
        self.assertEqual(os.listdir(self.tickets), [], 'A used ticket must be removed')
        replay, response, _ = self.login(ticket=ticket, handle=handle)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(replay.cookies.get('NS8_ADMIN'))

    def test_03_expired_ticket_is_refused(self):
        ticket = issue_ticket('owner1', self.tickets, now=time.time() - 120)
        session, response, _ = self.login(ticket=ticket)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(session.cookies.get('NS8_ADMIN'))

    def test_04_session_ends_without_renewal_and_lasts_with_it(self):
        renewed, response, handle = self.login('owner1')
        self.assertEqual(response.status_code, 200)
        expiring, response, _ = self.login('owner2')
        self.assertEqual(response.status_code, 200)
        for _ in range(3):
            time.sleep(SESSION_SECONDS / 2)
            self.assertEqual(self.renew('owner1', handle), 204)
        self.assertEqual(self.users(renewed), 200)
        # Without new tickets, e.g. after losing the NS8 right to get them
        self.assertEqual(self.users(expiring), 403)
        time.sleep(SESSION_SECONDS + 1)
        self.assertEqual(self.users(renewed), 403)
        self.assertEqual(self.renew('owner1', handle), 403, 'An expired session cannot be revived')

    def test_05_renewal_needs_the_handle_and_user_of_the_session(self):
        session, response, handle = self.login('owner1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.renew('owner1', secrets.token_urlsafe(32)), 403)
        self.assertEqual(self.renew('owner2', handle), 403)
        self.assertEqual(self.renew('owner1', handle, origin='https://attacker.example.test'), 403)
        self.assertEqual(self.renew('owner1', handle), 204)

    def test_06_backend_cookie_alone_is_no_bypass(self):
        worker = requests.Session()
        response = worker.post(self.base + '/admin/', data={'token': self.worker},
            headers={'X-NS8-Worker': self.worker}, timeout=15)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(worker.cookies.get('VW_ADMIN'))
        self.assertEqual(worker.get(self.base + '/admin/users', timeout=15).status_code, 403)
        api = AdminAPI(self.base, self.worker, self.directory.name)
        self.assertIsInstance(api.users(), list)

    def test_07_logout_destroys_server_session(self):
        session, response, _ = self.login('owner2')
        cookie = session.cookies.get('NS8_ADMIN')
        self.assertTrue(cookie)
        session.get(self.base + '/admin/logout', timeout=15)
        replay = requests.get(self.base + '/admin/users', cookies={'NS8_ADMIN': cookie}, timeout=15)
        self.assertEqual(replay.status_code, 403)

    def test_08_untrusted_login_origin_is_denied_without_using_the_ticket(self):
        ticket = issue_ticket('owner1', self.tickets)
        session, response, _ = self.login(ticket=ticket, origin='https://attacker.example.test')
        self.assertEqual(response.status_code, 401)
        self.assertFalse(session.cookies.get('NS8_ADMIN'))
        self.assertIn(hashlib.sha256(ticket.encode()).hexdigest(), os.listdir(self.tickets))

if __name__ == '__main__':
    unittest.main(verbosity=2)
