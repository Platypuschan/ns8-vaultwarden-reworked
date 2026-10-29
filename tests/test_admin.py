"""Owner action returns a one-time ticket; inactive apps never issue one."""
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, mock_open, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'imageroot/pypkg'))
import vaultwarden_admin
import vaultwarden_config
import vaultwarden_revoke


class AdminTests(unittest.TestCase):
    config = {'host': 'vault.example.test', 'domain': 'ad.example.test', 'idp_module': 'idp1'}

    def run_open_admin(self, directory, ancestors, user='admin'):
        output = io.StringIO()
        with patch('builtins.open', mock_open(read_data=json.dumps(self.config))), \
                patch('subprocess.run', return_value=Mock(returncode=0)), \
                patch.object(vaultwarden_admin, 'TICKET_DIR', directory), \
                patch.object(vaultwarden_config, 'env_value', return_value=ancestors), \
                patch.dict(os.environ, {'AGENT_TASK_USER': user}), \
                patch.object(sys, 'stdout', output):
            runpy.run_path(str(ROOT / 'imageroot/actions/open-admin/20open'))
        return json.loads(output.getvalue())

    def test_active_app_returns_a_one_time_ticket_for_the_configured_host(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_open_admin(directory, 'https://node1.example.test https://node2.example.test')
            ticket = result.pop('ticket')
            self.assertEqual(result, {
                'url': 'https://vault.example.test/admin/', 'session_seconds': 120,
                'revocation': {'state': 'pending', 'last_success': None, 'consecutive_errors': 0},
                'frame_ancestors': ['https://node1.example.test', 'https://node2.example.test']})
            # Only the hash of the ticket is stored, with the NS8 user
            files = os.listdir(directory)
            self.assertEqual(files, [hashlib.sha256(ticket.encode()).hexdigest()])
            stored = json.loads(Path(directory, files[0]).read_text())
            self.assertEqual(stored['user'], 'admin')
            self.assertNotIn(ticket, Path(directory, files[0]).read_text())
            self.assertLessEqual(stored['expires'] - time.time(), vaultwarden_admin.TICKET_SECONDS)
            self.assertEqual(Path(directory, files[0]).stat().st_mode & 0o777, 0o600)

    def test_installation_without_frame_ancestors_opens_a_tab(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.run_open_admin(directory, None)['frame_ancestors'], [])

    def test_ticket_requires_an_ns8_user(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                self.run_open_admin(directory, None, user='')
            self.assertEqual(os.listdir(directory), [])

    def test_unused_tickets_are_purged(self):
        with tempfile.TemporaryDirectory() as directory:
            vaultwarden_admin.issue_ticket('admin', directory, now=time.time() - 1000)
            old = os.listdir(directory)[0]
            os.utime(Path(directory, old), (time.time() - 1000,) * 2)
            vaultwarden_admin.issue_ticket('admin', directory)
            self.assertNotIn(old, os.listdir(directory))
            self.assertEqual(len(os.listdir(directory)), 1)

    def test_stopped_app_does_not_issue_a_ticket(self):
        output = io.StringIO()
        with patch('builtins.open', mock_open(read_data=json.dumps(self.config))), \
                patch('subprocess.run', return_value=Mock(returncode=3)), \
                patch.object(vaultwarden_admin, 'issue_ticket') as read, \
                patch.object(sys, 'stdout', output):
            with self.assertRaises(ValueError):
                runpy.run_path(str(ROOT / 'imageroot/actions/open-admin/20open'))
        self.assertEqual(output.getvalue(), '')
        read.assert_not_called()
