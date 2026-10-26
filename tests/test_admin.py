"""Owner action returns a direct login; inactive apps never disclose credentials."""
import io
import json
import os
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import Mock, mock_open, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'imageroot/pypkg'))
import vaultwarden_config
import vaultwarden_revoke


class AdminTests(unittest.TestCase):
    config = {'host': 'vault.example.test', 'domain': 'ad.example.test', 'idp_module': 'idp1'}

    def test_active_app_returns_login_for_the_configured_host(self):
        output = io.StringIO()
        with patch('builtins.open', mock_open(read_data=json.dumps(self.config))), \
                patch('subprocess.run', return_value=Mock(returncode=0)), \
                patch.object(vaultwarden_revoke, 'read_admin_token', return_value='t' * 64), \
                patch.object(vaultwarden_config, 'env_value', return_value='https://node1.example.test https://node2.example.test'), \
                patch.object(sys, 'stdout', output):
            runpy.run_path(str(ROOT / 'imageroot/actions/open-admin/20open'))
        self.assertEqual(json.loads(output.getvalue()), {
            'url': 'https://vault.example.test/admin/', 'token': 't' * 64,
            'frame_ancestors': ['https://node1.example.test', 'https://node2.example.test']})

    def test_installation_without_frame_ancestors_opens_a_tab(self):
        output = io.StringIO()
        with patch('builtins.open', mock_open(read_data=json.dumps(self.config))), \
                patch('subprocess.run', return_value=Mock(returncode=0)), \
                patch.object(vaultwarden_revoke, 'read_admin_token', return_value='t' * 64), \
                patch.object(vaultwarden_config, 'env_value', return_value=None), \
                patch.object(sys, 'stdout', output):
            runpy.run_path(str(ROOT / 'imageroot/actions/open-admin/20open'))
        self.assertEqual(json.loads(output.getvalue())['frame_ancestors'], [])

    def test_stopped_app_does_not_return_token(self):
        output = io.StringIO()
        with patch('builtins.open', mock_open(read_data=json.dumps(self.config))), \
                patch('subprocess.run', return_value=Mock(returncode=3)), \
                patch.object(vaultwarden_revoke, 'read_admin_token') as read, \
                patch.object(sys, 'stdout', output):
            with self.assertRaises(ValueError):
                runpy.run_path(str(ROOT / 'imageroot/actions/open-admin/20open'))
        self.assertEqual(output.getvalue(), '')
        read.assert_not_called()
