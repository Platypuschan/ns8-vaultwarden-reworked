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
            path.write_text('ADMIN_TOKEN=previously-exported\nSSO_CLIENT_SECRET=keep-this\nDOMAIN=https://vault.example.test\n')
            policy.rotate_worker_token(path)
            values = dict(line.split('=', 1) for line in path.read_text().splitlines())
            self.assertTrue(values['ADMIN_TOKEN'] != 'previously-exported')
            self.assertRegex(values['ADMIN_TOKEN'], policy.ADMIN_TOKEN)
            self.assertEqual(values['SSO_CLIENT_SECRET'], 'keep-this')
            self.assertEqual(values['DOMAIN'], 'https://vault.example.test')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

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
        self.assertEqual(parsed['ADMIN_TOKEN'],self.token)
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
        with tempfile.TemporaryDirectory() as d:
            env=Path(d)/'vaultwarden.env'
            new=policy.admin_token(env)
            self.assertRegex(new,r'^[A-Za-z0-9_-]{64}$')
            self.assertNotEqual(new,policy.admin_token(env))
            env.write_text(policy.environment(self.config,self.registration,new))
            self.assertEqual(policy.admin_token(env),new)

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
