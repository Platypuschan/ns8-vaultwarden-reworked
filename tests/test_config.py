import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'imageroot/pypkg'))
import vaultwarden_config as policy


HASH='$argon2id$v=19$m=19456,t=2,p=1$jXKqQhjZLkgo5+O0dKS+QmNa2/Fq00DnaduYD1Uip04$LJpdv4Ye7oqKDzpv81LyBMQMecsyVpPzm0ouUb4hSQ4'


def fake_hash(token):
    from test_worker_credential import real_hash
    return real_hash(token)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.config={'host':'vaultwarden.example.com','domain':'ad.example.com',
            'idp_module':'idp1','required_group':'services_vaultwarden','lets_encrypt':True}
        self.registration={'issuer':'https://sso.example.com/realms/ad.example.com',
            'client_id':'vaultwarden1','client_secret':'test-only-secret'}
        self.token='t'*64

    def test_upgrade_rotates_only_the_formerly_exported_worker_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'vaultwarden.env'
            token = Path(directory) / 'admin-worker.token'
            path.write_text('ADMIN_TOKEN=previously-exported\nSSO_CLIENT_SECRET=keep-this\nDOMAIN=https://vault.example.test\n')
            policy.rotate_worker_token(path, token, hasher=fake_hash)
            values = dict(line.split('=', 1) for line in path.read_text().splitlines())
            clear = policy.check_worker_credential(path, token)
            self.assertRegex(clear, policy.ADMIN_TOKEN)
            self.assertEqual(values['ADMIN_TOKEN'], fake_hash(clear))
            self.assertNotIn(clear, path.read_text())
            self.assertRegex(values['ADMIN_TOKEN'], policy.ADMIN_TOKEN_HASH)
            self.assertEqual(values['SSO_CLIENT_SECRET'], 'keep-this')
            self.assertEqual(values['DOMAIN'], 'https://vault.example.test')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual((Path(directory) / 'worker-credential.json').stat().st_mode & 0o777, 0o600)

    def test_failed_hashing_leaves_previous_pair_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'vaultwarden.env'
            token = Path(directory) / 'admin-worker.token'
            path.write_text('ADMIN_TOKEN=' + HASH + '\n')
            token.write_text('o' * 64 + '\n')
            def broken(_): raise RuntimeError('no podman')
            with self.assertRaises(RuntimeError):
                policy.rotate_worker_token(path, token, hasher=broken)
            self.assertEqual(path.read_text(), 'ADMIN_TOKEN=' + HASH + '\n')
            self.assertEqual(token.read_text(), 'o' * 64 + '\n')

    def test_admin_token_keeps_canonical_pair_and_repairs_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'vaultwarden.env'
            token = Path(directory) / 'admin-worker.token'
            # new installation
            first = policy.admin_token(path, token, hasher=fake_hash)
            self.assertRegex(first, policy.ADMIN_TOKEN_HASH)
            policy.private_write(path, 'ADMIN_TOKEN=' + first + '\n')
            clear = policy.check_worker_credential(path, token)
            self.assertEqual(policy.admin_token(path, token, hasher=fake_hash), first)
            self.assertEqual(policy.check_worker_credential(path, token), clear)
            # clear-text token of an earlier release
            path.write_text('ADMIN_TOKEN=' + 'c' * 64 + '\n')
            replaced = policy.admin_token(path, token, hasher=fake_hash)
            self.assertRegex(replaced, policy.ADMIN_TOKEN_HASH)
            self.assertEqual(policy.check_worker_credential(path, token), clear)
            # restored environment without the clear-text file
            path.write_text('ADMIN_TOKEN=' + replaced + '\n')
            token.unlink(missing_ok=True)
            self.assertEqual(policy.admin_token(path, token, hasher=fake_hash), replaced)
            self.assertEqual(policy.check_worker_credential(path, token), clear)

    def test_environment_accepts_a_hash_but_not_other_token_shapes(self):
        env = policy.environment(policy.validate(self.config), self.registration, HASH)
        self.assertIn('\nADMIN_TOKEN=' + HASH + '\n', '\n' + env)
        for bad in ('$argon2id$x', HASH + '\nSSO_ONLY=false', '$argon2i$v=19$m=1,t=1,p=1$' + 'A' * 16 + '$' + 'A' * 32, 'short'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                policy.environment(policy.validate(self.config), self.registration, bad)

    @unittest.skipUnless(os.environ.get('VW_RUNTIME_IMAGE'), 'needs podman and VW_RUNTIME_IMAGE')
    def test_runtime_image_makes_a_valid_argon2_hash(self):
        value = policy.argon2_hash('r' * 64, os.environ['VW_RUNTIME_IMAGE'])
        self.assertRegex(value, policy.ADMIN_TOKEN_HASH)
        self.assertNotIn('r' * 64, value)

    def test_policy_changes_require_explicit_matching_reconfiguration(self):
        state = {'enforced': False, 'enabled': True, 'group_path': '/services_vaultwarden',
            'issues': ['expected_group_mismatch'], 'policy_required': True,
            'policy_group_pinned': False, 'policy_consumer_bound': True}
        # Preflight may validate the newly proposed group before registration
        # binds it; the runtime worker must still reject this state.
        policy.require_policy(self.config, state, require_binding=False)
        with self.assertRaises(ValueError):
            policy.require_policy(self.config, state)
        state['group_path'] = '/some-other-group'
        with self.assertRaises(ValueError):
            policy.require_policy(self.config, state, require_binding=False)

    def test_sso_policy_cannot_fall_back_to_password(self):
        env=policy.environment(policy.validate(self.config),self.registration,self.token)
        parsed=dict(line.split('=',1) for line in env.splitlines())
        self.assertEqual(parsed['SSO_ONLY'],'true')
        self.assertEqual(parsed['SIGNUPS_ALLOWED'],'false')
        self.assertEqual(parsed['SSO_SIGNUPS_MATCH_EMAIL'],'false')
        self.assertEqual(parsed['SSO_ALLOW_UNKNOWN_EMAIL_VERIFICATION'],'false')
        self.assertEqual(parsed['SSO_AUTH_ONLY_NOT_SESSION'],'true')
        self.assertEqual(parsed['SSO_CLIENT_SECRET'],'test-only-secret')
        self.assertEqual(parsed['ADMIN_TOKEN'],self.token)  # raw still accepted by the generic validator
        self.assertEqual(parsed['NS8_MANAGED_CONFIG'],'true')
        self.assertEqual(parsed['ADMIN_RATELIMIT_MAX_BURST'],'30')
        self.assertEqual(parsed['ALLOWED_IFRAME_ANCESTORS'],'')

    def test_cluster_manager_may_embed_the_admin_page(self):
        ancestors=policy.frame_ancestors(['Node1.Example.COM.','node2.example.com','node1.example.com',
            'localhost','','bad host',None,'x;frame-ancestors *'])
        self.assertEqual(ancestors,'https://node1.example.com https://node2.example.com')
        env=policy.environment(self.config,self.registration,self.token,ancestors)
        parsed=dict(line.split('=',1) for line in env.splitlines())
        self.assertEqual(parsed['ALLOWED_IFRAME_ANCESTORS'],ancestors)
        self.assertEqual(policy.frame_ancestors([]),'')
        for value in ('*','https://a.test; script-src *','http://a.test','https://a.test\nSSO_ONLY=false',None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                policy.environment(self.config,self.registration,self.token,value)

    def test_admin_token_is_kept_and_validated(self):
        for token in ('', 'short', 'a'*60+'\nSSO_ONLY=false', 'a'*60+' x', None):
            with self.subTest(token=token), self.assertRaises(ValueError):
                policy.environment(self.config,self.registration,token)

    def test_input_and_env_injection_rejected(self):
        for field,value in [('host','bad\nSSO_ONLY=false'),('domain','ad.test/../../master'),
                            ('idp_module','idp1;id'),('required_group','/group'),('lets_encrypt','false')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                policy.validate(self.config|{field:value})
        with self.assertRaises(ValueError):
            policy.environment(self.config,self.registration|{'client_secret':'a\nSSO_ONLY=false'},self.token)

    def test_issuer_confusion_rejected(self):
        for issuer in ['http://sso.test/realms/ad.example.com',
                       'https://sso.test/realms/another.test',
                       'https://user:pass@sso.test/realms/ad.example.com',
                       'https://sso.test/realms/ad.example.com?x=1']:
            with self.subTest(issuer=issuer), self.assertRaises(ValueError):
                policy.environment(self.config,self.registration|{'issuer':issuer},self.token)

    def test_unprotected_or_wrong_group_rejected(self):
        for state in [{},{'enforced':False},{'enforced':True,'enabled':False,'group_path':'/services_vaultwarden'},
                      {'enforced':True,'enabled':True,'policy_required':True,'policy_group_pinned':True,'policy_consumer_bound':True,'group_path':'/other'}]:
            with self.subTest(state=state),self.assertRaises(ValueError):
                policy.require_policy(self.config,state)
        policy.require_policy(self.config,{'enforced':True,'enabled':True,'policy_required':True,'policy_group_pinned':True,'policy_consumer_bound':True,'group_path':'/services_vaultwarden'})

    def test_secret_write_is_private_and_replaces_atomically(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'vaultwarden.env'
            p.write_text('old')
            p.chmod(0o644)
            policy.private_write(p,'new secret')
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
            self.assertEqual(p.read_text(),'new secret')
            self.assertEqual([p.name for p in Path(d).iterdir()],['vaultwarden.env'])

if __name__=='__main__': unittest.main()
