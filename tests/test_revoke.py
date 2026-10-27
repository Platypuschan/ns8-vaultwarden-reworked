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
    def deauth(self, user_id):
        self.calls.append(('deauth', user_id))



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

    def test_non_members_are_logged_out_and_never_disabled(self):
        before = dict(self.api.accounts['b'])
        report = self.reconcile({'alice@example.test', 'carol@example.test'})
        self.assertEqual(report, {'deauthenticated': 1, 'legacy_disabled': 0})
        self.assertEqual(self.api.calls, [('deauth', 'b')])
        self.assertEqual(self.api.accounts['b'], before)
        self.reconcile({'alice@example.test', 'bob@example.test', 'carol@example.test'})
        self.assertEqual(len(self.api.calls), 1)
        self.assertFalse(self.api.accounts['c']['userEnabled'])

    def test_legacy_sperren_are_never_automatically_cleared(self):
        path = Path(self.dir.name) / revoke.REVOKED_FILE
        path.write_text(json.dumps({'c': 'carol@example.test'}))
        report = self.reconcile({'alice@example.test', 'bob@example.test', 'carol@example.test'})
        self.assertFalse(self.api.accounts['c']['userEnabled'])
        self.assertEqual(self.api.calls, [])
        self.assertEqual(report['legacy_disabled'], 1)
        self.assertEqual(json.loads(path.read_text()), {'c': 'carol@example.test'})

    def test_empty_group_logs_out_all_accounts_even_manually_disabled(self):
        report = self.reconcile(set())
        self.assertEqual(report['deauthenticated'], 3)
        self.assertEqual(set(self.api.calls), {('deauth', 'a'), ('deauth', 'b'), ('deauth', 'c')})

    def test_partial_failure_can_be_retried_without_lock_bookkeeping(self):
        def interrupted(user):
            raise revoke.RevokeError('injected failure')
        original = self.api.deauth
        self.api.deauth = interrupted
        with self.assertRaises(revoke.RevokeError):
            self.reconcile(set())
        self.api.deauth = original
        self.assertEqual(self.reconcile(set())['deauthenticated'], 3)
        self.assertFalse((Path(self.dir.name) / revoke.REVOKED_FILE).exists())

    def test_status_preserves_last_success_and_warns_after_repeated_errors(self):
        success = revoke.write_status(report={'legacy_disabled': 2}, state_dir=self.dir.name)
        self.assertEqual(revoke.status(self.dir.name)['state'], 'ok')
        for i in range(3):
            error = revoke.write_status(error='LDAP unavailable', state_dir=self.dir.name)
        status = revoke.status(self.dir.name)
        self.assertEqual(status['state'], 'warning')
        self.assertEqual(status['last_success'], success['last_success'])
        self.assertEqual(status['consecutive_errors'], 3)
        self.assertEqual(status['legacy_disabled'], 2)
        revoke.write_status(state_dir=self.dir.name)
        self.assertEqual(revoke.status(self.dir.name)['state'], 'ok')

    def test_monitor_that_never_runs_warns_after_startup_grace(self):
        from datetime import datetime, timezone, timedelta
        revoke.initialize_status(self.dir.name)
        self.assertEqual(revoke.status(self.dir.name)['state'], 'pending')
        path = Path(self.dir.name) / revoke.STATUS_FILE
        data = json.loads(path.read_text())
        data['monitor_started'] = (datetime.now(timezone.utc) - timedelta(minutes=7)).isoformat()
        path.write_text(json.dumps(data))
        self.assertEqual(revoke.status(self.dir.name)['state'], 'warning')

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
