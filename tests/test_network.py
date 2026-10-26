"""Local pasta routing, relocation, stale state and discovery failures."""
import json
import contextlib
import io
from pathlib import Path
import sys
import runpy
import tempfile
import unittest
import types
from unittest.mock import Mock, patch, mock_open

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'imageroot/pypkg'))
import vaultwarden_network as network


class NetworkTests(unittest.TestCase):
    config = {'domain': 'ad.test', 'idp_module': 'idp-reworked1'}
    issuer = 'https://sso.test/realms/ad.test'

    def test_local_pasta_uses_dynamic_host_gateway(self):
        self.assertEqual(network.network_options(self.config, self.issuer, '2', '2', 'pasta'),
            ['--add-host=sso.test:host-gateway'])

    def test_remote_idp_and_other_backends_keep_dns(self):
        for local, remote, backend in [('1', '2', 'pasta'), ('2', '2', 'slirp4netns')]:
            with self.subTest(backend=backend, remote=remote):
                self.assertEqual(network.network_options(self.config, self.issuer, local, remote, backend), [])

    def test_unknown_node_and_unsafe_issuers_fail(self):
        for issuer in [self.issuer, 'http://sso.test/realms/ad.test',
                'https://sso.test/realms/other.test', 'https://sso.test;bad/realms/ad.test']:
            with self.subTest(issuer=issuer):
                with self.assertRaises(ValueError):
                    network.network_options(self.config, issuer, '2', None, 'pasta')
        with self.assertRaises(ValueError):
            network.network_options(self.config, 'https://sso.test;bad/realms/ad.test', '2', '2', 'pasta')

    def test_start_recomputes_mapping_after_idp_moves(self):
        rdb = Mock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'network.env'
            original_write = network.policy.private_write
            with patch.object(network.subprocess, 'check_output', return_value='pasta\n'), \
                    patch.object(network.policy, 'private_write',
                        side_effect=lambda name, content: original_write(path, content)):
                rdb.hget.return_value = '2'
                network.prepare_network(self.config, self.issuer, rdb, '2')
                self.assertIn('sso.test:host-gateway', path.read_text())
                rdb.hget.return_value = '3'
                network.prepare_network(self.config, self.issuer, rdb, '2')
                self.assertEqual(path.read_text(), 'VAULTWARDEN_NETWORK_ARGS=\n')
        rdb.hget.assert_called_with('cluster/module_node', 'idp-reworked1')

    def test_issuer_read_does_not_split_query_or_secret_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'env'
            path.write_text('SSO_CLIENT_SECRET=abc=def\nSSO_AUTHORITY=' + self.issuer + '\n')
            self.assertEqual(network.read_issuer(path), self.issuer)

    def test_discovery_requires_https_success_and_matching_issuer(self):
        for code, body in [(7, ''), (60, ''), (0, '{}'), (0, 'not json'),
                (0, json.dumps({'issuer': 'https://wrong.test'}))]:
            with self.subTest(code=code, body=body), \
                    patch.object(network.subprocess, 'run', return_value=Mock(returncode=code, stdout=body)):
                with self.assertRaisesRegex(ValueError, 'OIDC discovery failed'):
                    network.check_discovery(self.issuer, timeout=0)
        with patch.object(network.subprocess, 'run', return_value=Mock(
                returncode=0, stdout=json.dumps({'issuer': self.issuer}))) as run:
            network.check_discovery(self.issuer, timeout=0)
            self.assertNotIn('-k', run.call_args.args[0])
            self.assertIn('vaultwarden-app', run.call_args.args[0])

    def test_discovery_retries_while_certificate_is_issued(self):
        with patch.object(network.subprocess, 'run', side_effect=[
                Mock(returncode=60, stdout=''),
                Mock(returncode=0, stdout=json.dumps({'issuer': self.issuer}))]) as run, \
                patch.object(network.time, 'sleep'):
            network.check_discovery(self.issuer)
            self.assertEqual(run.call_count, 2)


class ConfigureDiscoveryTests(unittest.TestCase):
    def configure(self, lets_encrypt, failure=False):
        config = {'host': 'vault.test', 'domain': 'ad.test', 'idp_module': 'idp1',
            'required_group': 'services_vaultwarden', 'lets_encrypt': lets_encrypt}
        agent = types.ModuleType('agent')
        tasks = types.ModuleType('agent.tasks')
        tasks.run = Mock(return_value={'exit_code': 0})
        agent.tasks = tasks
        agent.exclusive_file_lock = lambda name: contextlib.nullcontext()
        agent.resolve_agent_id = Mock(return_value='module/traefik1')
        agent.assert_exp = lambda condition, message: self.assertTrue(condition, message)
        sso = types.ModuleType('vaultwarden_sso')
        sso.task = Mock(return_value={'enforced': True, 'enabled': True,
            'group_path': '/services_vaultwarden'})
        sso.prepare = Mock(return_value={'issuer': 'https://sso.test/realms/ad.test'})
        sso.configure_admin_route = Mock()
        output = io.StringIO()
        with patch.dict(sys.modules, {'agent': agent, 'agent.tasks': tasks, 'vaultwarden_sso': sso}), \
                patch('builtins.open', mock_open(read_data=json.dumps(config))), \
                patch.object(sys, 'stdin', io.StringIO(json.dumps(config))), \
                patch.object(sys, 'stdout', output), \
                patch.dict('os.environ', {'MODULE_ID': 'vaultwarden1', 'TCP_PORT': '20001'}), \
                patch('subprocess.run'), \
                patch.object(network, 'check_discovery',
                    side_effect=ValueError('OIDC discovery failed') if failure else None) as check:
            if failure:
                with self.assertRaisesRegex(ValueError, 'OIDC discovery failed'):
                    runpy.run_path(str(ROOT / 'imageroot/actions/configure-module/20configure'))
                self.assertEqual(output.getvalue(), '')
            else:
                runpy.run_path(str(ROOT / 'imageroot/actions/configure-module/20configure'))
        return output.getvalue(), check

    def test_automatic_https_is_verified_before_reporting_success(self):
        output, check = self.configure(True)
        self.assertTrue(json.loads(output)['oidc_verified'])
        check.assert_called_once_with('https://sso.test/realms/ad.test')

    def test_discovery_failure_does_not_report_configured(self):
        self.configure(True, failure=True)

    def test_manual_certificate_configuration_explicitly_unverified(self):
        output, check = self.configure(False)
        self.assertFalse(json.loads(output)['oidc_verified'])
        check.assert_not_called()


if __name__ == '__main__':
    unittest.main()
