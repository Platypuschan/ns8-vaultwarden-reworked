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

    def test_sso_policy_cannot_fall_back_to_password(self):
        env=policy.environment(policy.validate(self.config),self.registration)
        parsed=dict(line.split('=',1) for line in env.splitlines())
        self.assertEqual(parsed['SSO_ONLY'],'true')
        self.assertEqual(parsed['SIGNUPS_ALLOWED'],'false')
        self.assertEqual(parsed['SSO_SIGNUPS_MATCH_EMAIL'],'false')
        self.assertEqual(parsed['SSO_ALLOW_UNKNOWN_EMAIL_VERIFICATION'],'false')
        self.assertEqual(parsed['SSO_AUTH_ONLY_NOT_SESSION'],'false')
        self.assertEqual(parsed['SSO_CLIENT_SECRET'],'test-only-secret')

    def test_input_and_env_injection_rejected(self):
        for field,value in [('host','bad\nSSO_ONLY=false'),('domain','ad.test/../../master'),
                            ('idp_module','idp1;id'),('required_group','/group'),('lets_encrypt','false')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                policy.validate(self.config|{field:value})
        with self.assertRaises(ValueError):
            policy.environment(self.config,self.registration|{'client_secret':'a\nSSO_ONLY=false'})

    def test_issuer_confusion_rejected(self):
        for issuer in ['http://sso.test/realms/ad.example.com',
                       'https://sso.test/realms/another.test',
                       'https://user:pass@sso.test/realms/ad.example.com',
                       'https://sso.test/realms/ad.example.com?x=1']:
            with self.subTest(issuer=issuer), self.assertRaises(ValueError):
                policy.environment(self.config,self.registration|{'issuer':issuer})

    def test_unprotected_or_wrong_group_rejected(self):
        for state in [{},{'enforced':False},{'enforced':True,'enabled':False,'group_path':'/services_vaultwarden'},
                      {'enforced':True,'enabled':True,'group_path':'/other'}]:
            with self.subTest(state=state),self.assertRaises(ValueError):
                policy.require_policy(self.config,state)
        policy.require_policy(self.config,{'enforced':True,'enabled':True,'group_path':'/services_vaultwarden'})

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
