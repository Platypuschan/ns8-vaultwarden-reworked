"""Revocation of the Vaultwarden accounts of users outside the AD group."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'imageroot/pypkg'))
import vaultwarden_revoke as revoke


HASH='$argon2id$v=19$m=19456,t=2,p=1$jXKqQhjZLkgo5+O0dKS+QmNa2/Fq00DnaduYD1Uip04$LJpdv4Ye7oqKDzpv81LyBMQMecsyVpPzm0ouUb4hSQ4'

class FakeAdmin:
    def __init__(self, users):
        self.accounts={u['id']:dict(u) for u in users}
        self.calls=[]
    def users(self):
        return [dict(u) for u in self.accounts.values()]
    def deauth(self, user_id):
        self.calls.append(('deauth', user_id))
        # Like Vaultwarden: all devices are deleted
        self.accounts[user_id]['lastActive'] = None
    def login(self, user_id):
        self.accounts[user_id]['lastActive'] = '2026-11-08 12:00:00'



class RevokeTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.api=FakeAdmin([
            {'id':'a','email':'Alice@Example.test','userEnabled':True,'lastActive':'2026-11-01 10:00:00'},
            {'id':'b','email':'bob@example.test','userEnabled':True,'lastActive':'2026-11-01 10:00:00'},
            # Disabled by an administrator
            {'id':'c','email':'carol@example.test','userEnabled':False,'lastActive':None},
        ])
    def reconcile(self, members):
        return revoke.reconcile(self.api,members,self.dir.name)

    def test_non_members_are_logged_out_and_never_disabled(self):
        before = dict(self.api.accounts['b'])
        report = self.reconcile({'alice@example.test', 'carol@example.test'})
        self.assertEqual(report, {'deauthenticated': 1, 'skipped': 0, 'failed': 0, 'legacy_disabled': 0})
        self.assertEqual(self.api.calls, [('deauth', 'b')])
        self.assertEqual({k: v for k, v in self.api.accounts['b'].items() if k != 'lastActive'}, {k: v for k, v in before.items() if k != 'lastActive'})
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

    def test_one_failing_user_does_not_stop_the_others(self):
        original = self.api.deauth
        def first_fails(user):
            if user == 'a':
                raise revoke.RevokeError('Vaultwarden admin API POST users: HTTP 500')
            original(user)
        self.api.deauth = first_fails
        report = self.reconcile(set())
        self.assertEqual(report['failed'], 1)
        self.assertEqual(report['deauthenticated'], 2)
        self.assertEqual(set(self.api.calls), {('deauth', 'b'), ('deauth', 'c')})
        self.api.deauth = original
        report = self.reconcile(set())
        self.assertEqual((report['deauthenticated'], report['skipped']), (1, 2))
        self.assertFalse((Path(self.dir.name) / revoke.REVOKED_FILE).exists())

    def test_unreachable_vaultwarden_stops_the_run(self):
        def unreachable(user):
            self.api.calls.append(('deauth', user))
            raise revoke.UnavailableError('Vaultwarden is not reachable: URLError')
        self.api.deauth = unreachable
        with self.assertRaises(revoke.UnavailableError):
            self.reconcile(set())
        self.assertEqual(len(self.api.calls), 1)

    def test_ended_nonmember_without_devices_is_skipped_until_a_new_login(self):
        self.reconcile(set())
        self.assertEqual(len(self.api.calls), 3)
        report = self.reconcile(set())
        self.assertEqual((report['deauthenticated'], report['skipped']), (0, 3))
        self.assertEqual(len(self.api.calls), 3)
        self.api.login('b')
        report = self.reconcile(set())
        self.assertEqual((report['deauthenticated'], report['skipped']), (1, 2))
        self.assertEqual(self.api.calls[-1], ('deauth', 'b'))

    def test_without_proof_of_an_earlier_logout_a_deviceless_user_is_still_logged_out(self):
        self.api.accounts['a']['lastActive'] = None
        self.reconcile({'bob@example.test'})
        self.assertIn(('deauth', 'a'), self.api.calls)

    def test_regained_membership_forgets_the_proof(self):
        self.reconcile(set())
        self.reconcile({'bob@example.test'})
        self.reconcile(set())
        self.assertEqual(self.api.calls.count(('deauth', 'b')), 2)

    def test_failed_logout_is_never_remembered_and_removed_users_are_dropped(self):
        original = self.api.deauth
        def fails(user):
            raise revoke.RevokeError('HTTP 500')
        self.api.deauth = fails
        self.reconcile(set())
        self.assertEqual(revoke._load_ended(self.dir.name), set())
        self.api.deauth = original
        self.reconcile(set())
        del self.api.accounts['a']
        self.reconcile(set())
        self.assertEqual(revoke._load_ended(self.dir.name), {'b', 'c'})

    def test_status_keeps_the_reason(self):
        revoke.write_status(error='IdP too old', state_dir=self.dir.name, reason='idp_update_required')
        self.assertEqual(revoke.status(self.dir.name)['reason'], 'idp_update_required')
        revoke.write_status(state_dir=self.dir.name)
        self.assertNotIn('reason', revoke.status(self.dir.name))

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

    def test_worker_token_comes_from_its_file_not_from_the_hash(self):
        env=Path(self.dir.name)/'vaultwarden.env'
        token=Path(self.dir.name)/'admin-worker.token'
        clear='w'*64
        env.write_text('SSO_ONLY=true\nADMIN_TOKEN='+HASH+'\n')
        with self.assertRaises(revoke.RevokeError):
            revoke.read_admin_token(token,env)
        token.write_text(clear+'\n')
        self.assertEqual(revoke.read_admin_token(token,env),clear)

    def test_clear_text_environment_token_of_earlier_releases_still_works_until_update(self):
        env=Path(self.dir.name)/'vaultwarden.env'
        token=Path(self.dir.name)/'admin-worker.token'
        env.write_text('SSO_ONLY=true\nADMIN_TOKEN=abc\n')
        self.assertEqual(revoke.read_admin_token(token,env),'abc')
        env.write_text('SSO_ONLY=true\n')
        with self.assertRaises(revoke.RevokeError):
            revoke.read_admin_token(token,env)


if __name__=='__main__': unittest.main()
