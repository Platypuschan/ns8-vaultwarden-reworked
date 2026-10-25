"""Revocation of the Vaultwarden accounts of users outside the AD group."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'imageroot/pypkg'))
import vaultwarden_revoke as revoke


class FakeAdmin:
    def __init__(self, users):
        self.accounts={u['id']:dict(u) for u in users}
        self.calls=[]
    def users(self):
        return [dict(u) for u in self.accounts.values()]
    def disable(self, user_id):
        self.calls.append(('disable',user_id))
        self.accounts[user_id]['userEnabled']=False
    def enable(self, user_id):
        self.calls.append(('enable',user_id))
        self.accounts[user_id]['userEnabled']=True


class RevokeTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.api=FakeAdmin([
            {'id':'a','email':'Alice@Example.test','userEnabled':True},
            {'id':'b','email':'bob@example.test','userEnabled':True},
            # Disabled by an administrator
            {'id':'c','email':'carol@example.test','userEnabled':False},
        ])
    def reconcile(self, members):
        return revoke.reconcile(self.api,members,self.dir.name)

    def test_non_members_are_disabled_once(self):
        report=self.reconcile({'alice@example.test','carol@example.test'})
        self.assertEqual(report,{'disabled':['bob@example.test'],'enabled':[]})
        self.assertEqual(self.api.calls,[('disable','b')])
        self.assertEqual(self.reconcile({'alice@example.test'}),{'disabled':[],'enabled':[]})
        self.assertEqual(len(self.api.calls),1)
        stored=Path(self.dir.name)/revoke.REVOKED_FILE
        self.assertEqual(stored.stat().st_mode & 0o777,0o600)
        self.assertEqual(json.loads(stored.read_text()),{'b':'bob@example.test'})

    def test_members_again_are_enabled_but_not_admin_disabled_accounts(self):
        self.reconcile({'alice@example.test'})
        report=self.reconcile({'alice@example.test','bob@example.test','carol@example.test'})
        self.assertEqual(report,{'disabled':[],'enabled':['bob@example.test']})
        self.assertFalse(self.api.accounts['c']['userEnabled'])
        self.assertEqual(json.loads((Path(self.dir.name)/revoke.REVOKED_FILE).read_text()),{})

    def test_account_enabled_by_an_administrator_is_forgotten(self):
        self.reconcile({'alice@example.test'})
        self.api.accounts['b']['userEnabled']=True
        self.reconcile({'alice@example.test','bob@example.test'})
        self.assertEqual(json.loads((Path(self.dir.name)/revoke.REVOKED_FILE).read_text()),{})

    def test_empty_group_disables_everybody(self):
        report=self.reconcile(set())
        self.assertEqual(sorted(report['disabled']),['alice@example.test','bob@example.test'])

    def test_members_filter_is_direct_and_excludes_disabled_accounts(self):
        f=revoke.members_filter('CN=g (x),DC=ad,DC=test','(!(sAMAccountName=svc))')
        self.assertIn('(memberOf=CN=g \\28x\\29,DC=ad,DC=test)',f)
        self.assertNotIn('1.2.840.113556.1.4.1941',f)
        self.assertIn('(!(userAccountControl:1.2.840.113556.1.4.803:=2))',f)
        self.assertIn('(!(sAMAccountName=svc))',f)

    def test_filter_escaping_matches_ldap3(self):
        for value in ('CN=a*b,DC=x', 'CN=(x)\\y', 'CN=nul\0', 'CN=Jürgen'):
            with self.subTest(value=value):
                expected={'*':'\\2a','(':'\\28',')':'\\29','\\':'\\5c','\0':'\\00'}
                self.assertEqual(revoke.escape_filter_chars(value),''.join(expected.get(c,c) for c in value))

    def test_admin_token_is_read_from_the_environment(self):
        env=Path(self.dir.name)/'vaultwarden.env'
        env.write_text('SSO_ONLY=true\nADMIN_TOKEN=abc\n')
        self.assertEqual(revoke.read_admin_token(env),'abc')
        env.write_text('SSO_ONLY=true\n')
        with self.assertRaises(revoke.RevokeError):
            revoke.read_admin_token(env)


if __name__=='__main__': unittest.main()
