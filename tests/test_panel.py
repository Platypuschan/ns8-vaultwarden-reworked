"""Backend and static checks of the native module pages."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'imageroot/pypkg'))
import vaultwarden_config as policy
import vaultwarden_panel as panel
import vaultwarden_revoke as revoke

USER = '11111111-2222-3333-4444-555555555555'
ORG = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'


def element(name, value=None, default=None, kind='text', editable=True):
    return {'name': name, 'value': value, 'default': default, 'type': kind, 'editable': editable,
        'doc': {'name': name, 'description': ''}, 'overridden': False}


RAW = [
    {'group': 'settings', 'groupdoc': 'General settings', 'grouptoggle': '', 'elements': [
        element('signups_verify', True, False, 'checkbox'),
        element('org_creation_users', None, None),
        element('domain', 'https://x', None, editable=False),
        element('incomplete_2fa_time_limit', 3, 3, 'number'),
    ]},
    {'group': 'sso', 'groupdoc': 'OpenID Connect SSO settings', 'grouptoggle': '', 'elements': [
        element('sso_client_secret', '********', '********', 'password', editable=False)]},
    {'group': 'yubico', 'groupdoc': 'Yubikey settings', 'grouptoggle': '_enable_yubico', 'elements': [
        element('yubico_client_id', 'abc', None)]},
    {'group': 'smtp', 'groupdoc': 'SMTP Email Settings', 'grouptoggle': '_enable_smtp', 'elements': [
        element('smtp_host', None, None), element('smtp_port', 587, 587, 'number'),
        element('smtp_password', None, None, 'password')]},
    {'group': 'jobs', 'groupdoc': '', 'grouptoggle': '', 'elements': [
        element('job_poll_interval_ms', 30000, 30000, 'number', editable=False)]},
]


class FakeConnection:
    def __init__(self, answers=None):
        self.calls = []
        self.answers = answers or {}

    def request(self, method, path, payload=None, timeout=30):
        self.calls.append((method, path, payload))
        return self.answers.get(path)


class SettingsTests(unittest.TestCase):
    def test_only_the_offered_groups_and_editable_fields_are_visible(self):
        groups = panel.visible_settings(RAW)
        self.assertEqual([g['group'] for g in groups], ['settings', 'smtp'])
        names = [e['name'] for g in groups for e in g['elements']]
        self.assertNotIn('domain', names)
        self.assertNotIn('sso_client_secret', names)
        self.assertNotIn('yubico_client_id', names)
        self.assertIn('signups_verify', names)

    def test_save_sends_the_complete_config_so_other_groups_survive(self):
        merged = panel.merged_settings(RAW, {'smtp_host': 'mail.example.org'})
        # Vaultwarden replaces the whole file: Yubikey and the earlier value stay
        self.assertEqual(merged, {'signups_verify': True, 'yubico_client_id': 'abc', 'smtp_host': 'mail.example.org'})

    def test_clearing_or_defaulting_a_value_removes_it(self):
        merged = panel.merged_settings(RAW, {'signups_verify': False, 'smtp_port': 25})
        self.assertNotIn('signups_verify', merged)
        self.assertEqual(merged['smtp_port'], 25)
        self.assertNotIn('smtp_port', panel.merged_settings(RAW, {'smtp_port': '587'}))

    def test_managed_hidden_and_unknown_fields_are_refused(self):
        for name in ('domain', 'sso_client_secret', 'yubico_client_id', 'admin_token', 'nonsense'):
            with self.assertRaises(ValueError, msg=name):
                panel.merged_settings(RAW, {name: 'x'})

    def test_value_types_are_checked(self):
        with self.assertRaises(ValueError):
            panel.merged_settings(RAW, {'signups_verify': 'yes'})
        with self.assertRaises(ValueError):
            panel.merged_settings(RAW, {'smtp_port': 'abc'})
        with self.assertRaises(ValueError):
            panel.merged_settings(RAW, {'smtp_host': 5})
        with self.assertRaises(ValueError):
            panel.merged_settings(RAW, {})
        self.assertEqual(panel.merged_settings(RAW, {'smtp_port': ''})['signups_verify'], True)

    def test_save_posts_to_the_admin_api(self):
        connection = FakeConnection({'/admin/ns8/data/settings': RAW})
        panel.save_settings({'smtp_host': 'mail.example.org'}, connection)
        self.assertEqual(connection.calls[-1][:2], ('POST', '/admin/config'))
        self.assertEqual(connection.calls[-1][2]['smtp_host'], 'mail.example.org')

    def test_reset_deletes_the_user_config(self):
        connection = FakeConnection()
        panel.reset_settings(connection)
        self.assertEqual(connection.calls, [('POST', '/admin/config/delete', None)])


class UserAndOrganizationTests(unittest.TestCase):
    def test_users_are_reduced_to_what_the_page_shows(self):
        user = {'id': USER, 'name': 'A', 'email': 'a@example.org', 'key': 'secret-key', 'privateKey': 'private',
            'securityStamp': 'stamp', 'accountKeys': {'x': 1}, 'user_enabled': True, 'twoFactorEnabled': False,
            'organizations': [{'id': ORG, 'name': 'Org', 'type': 0, 'key': 'orgkey'}]}
        slim = panel.slim_users([user])[0]
        self.assertNotIn('key', slim)
        self.assertNotIn('privateKey', slim)
        self.assertNotIn('securityStamp', slim)
        self.assertNotIn('accountKeys', slim)
        self.assertEqual(slim['organizations'], [{'id': ORG, 'name': 'Org', 'type': '0'}])
        self.assertNotIn('key', json.dumps(slim['organizations']))

    def test_organizations_are_reduced(self):
        organization = {'id': ORG, 'name': 'Org', 'billingEmail': 'b@example.org', 'user_count': 2, 'identifier': 'i', 'seats': None}
        self.assertEqual(set(panel.slim_organizations([organization])[0]), set(panel.ORGANIZATION_FIELDS))

    def test_user_operations_use_the_matching_endpoint(self):
        expected = {'delete': ('POST', 'delete'), 'deauth': ('POST', 'deauth'), 'disable': ('POST', 'disable'),
            'enable': ('POST', 'enable'), 'remove-2fa': ('POST', 'remove-2fa'), 'delete-sso': ('DELETE', 'sso')}
        for operation, (method, suffix) in expected.items():
            connection = FakeConnection()
            panel.manage_user(operation, USER, connection=connection)
            self.assertEqual(connection.calls, [(method, f'/admin/users/{USER}/{suffix}', None)])

    def test_role_change_and_resync(self):
        connection = FakeConnection()
        panel.manage_user('set-org-role', USER, role='manager', org_id=ORG, connection=connection)
        self.assertEqual(connection.calls, [('POST', '/admin/users/org_type',
            {'user_type': 3, 'user_uuid': USER, 'org_uuid': ORG})])
        connection = FakeConnection()
        panel.manage_user('resync-all', connection=connection)
        self.assertEqual(connection.calls, [('POST', '/admin/users/update_revision', None)])

    def test_invalid_identifiers_never_reach_the_api(self):
        connection = FakeConnection()
        for call in (lambda: panel.manage_user('delete', '../x', connection=connection),
                lambda: panel.manage_user('delete', None, connection=connection),
                lambda: panel.manage_user('explode', USER, connection=connection),
                lambda: panel.manage_user('set-org-role', USER, role='root', org_id=ORG, connection=connection),
                lambda: panel.manage_user('set-org-role', USER, role='user', org_id='x', connection=connection),
                lambda: panel.delete_organization('../x', connection)):
            with self.assertRaises(ValueError):
                call()
        self.assertEqual(connection.calls, [])

    def test_organization_delete_and_smtp_test(self):
        connection = FakeConnection()
        panel.delete_organization(ORG, connection)
        panel.test_smtp('a@example.org', connection)
        self.assertEqual(connection.calls, [('POST', f'/admin/organizations/{ORG}/delete', None),
            ('POST', '/admin/test/smtp', {'email': 'a@example.org'})])
        with self.assertRaises(ValueError):
            panel.test_smtp('not an address', connection)

    def test_unknown_section_is_refused(self):
        with self.assertRaises(ValueError):
            panel.get_data('config/backup', FakeConnection())

    def test_vaultwarden_error_text_is_kept(self):
        self.assertEqual(revoke._error_detail(b'{"ErrorModel":{"Message":"Cannot delete the last owner"}}'),
            'Cannot delete the last owner')
        self.assertEqual(revoke._error_detail(b'<html>'), '')


HOST = 'vault.example.org'
SMARTHOST = {'enabled': True, 'host': 'smtp.example.org', 'port': 465, 'username': 'user', 'password': 'pa ss#word',
    'encrypt_smtp': 'tls', 'tls_verify': True}


class SmtpModeTests(unittest.TestCase):
    def test_custom_mode_manages_nothing(self):
        self.assertEqual(policy.smtp_lines('custom'), [])
        self.assertEqual(policy.apply_smtp('A=1\nSMTP_HOST=old\n', 'custom'), 'A=1\n')

    def test_disabled_mode_turns_mail_off_and_locks_the_connection(self):
        lines = dict(line.split('=', 1) for line in policy.smtp_lines('disabled'))
        self.assertEqual((lines['_ENABLE_SMTP'], lines['USE_SENDMAIL']), ('false', 'false'))
        self.assertIn('smtp_host', lines['NS8_MANAGED_FIELDS'].split(','))
        self.assertIn('smtp_from', lines['NS8_MANAGED_FIELDS'].split(','))

    def test_smarthost_values_are_taken_over_but_sender_stays_editable(self):
        lines = dict(line.split('=', 1) for line in policy.smtp_lines('smarthost', SMARTHOST, HOST))
        self.assertEqual((lines['SMTP_HOST'], lines['SMTP_PORT'], lines['SMTP_SECURITY']),
            ('smtp.example.org', '465', 'force_tls'))
        self.assertEqual((lines['SMTP_USERNAME'], lines['SMTP_PASSWORD']), ('user', 'pa ss#word'))
        self.assertEqual(lines['SMTP_ACCEPT_INVALID_CERTS'], 'false')
        managed = lines['NS8_MANAGED_FIELDS'].split(',')
        self.assertIn('smtp_password', managed)
        self.assertNotIn('smtp_from', managed)
        self.assertNotIn('smtp_from_name', managed)

    def test_smarthost_encryption_and_certificate_check_mapping(self):
        lines = dict(line.split('=', 1) for line in policy.smtp_lines('smarthost',
            dict(SMARTHOST, encrypt_smtp='starttls', tls_verify=False, port=587), HOST))
        self.assertEqual(lines['SMTP_SECURITY'], 'starttls')
        self.assertEqual(lines['SMTP_ACCEPT_INVALID_CERTS'], 'true')
        lines = dict(line.split('=', 1) for line in policy.smtp_lines('smarthost', dict(SMARTHOST, encrypt_smtp='none'), HOST))
        self.assertEqual(lines['SMTP_SECURITY'], 'off')

    def test_smarthost_mode_has_a_sender_vaultwarden_accepts(self):
        # Vaultwarden refuses to start with SMTP_HOST but no SMTP_FROM
        lines = dict(line.split('=', 1) for line in policy.smtp_lines('smarthost', SMARTHOST, HOST))
        self.assertEqual(lines['SMTP_FROM'], 'no-reply@vault.example.org')
        lines = dict(line.split('=', 1) for line in policy.smtp_lines('smarthost', dict(SMARTHOST, username='relay@example.org'), HOST))
        self.assertEqual(lines['SMTP_FROM'], 'relay@example.org')
        with self.assertRaises(ValueError):
            policy.smtp_lines('smarthost', SMARTHOST)

    def test_smarthost_mode_needs_a_smarthost(self):
        for smarthost in (None, {}, {'enabled': False, 'host': 'h'}, {'enabled': True, 'host': ''}):
            with self.assertRaises(ValueError):
                policy.smtp_lines('smarthost', smarthost, HOST)
        with self.assertRaises(ValueError):
            policy.smtp_lines('other')

    def test_new_mode_replaces_earlier_lines_and_keeps_other_values(self):
        env = 'DOMAIN=https://vault\nADMIN_TOKEN=$argon2id$x\n'
        first = policy.apply_smtp(env, 'smarthost', SMARTHOST, HOST)
        second = policy.apply_smtp(first, 'disabled')
        self.assertTrue(second.startswith(env))
        self.assertNotIn('SMTP_HOST', second)
        self.assertNotIn('pa ss#word', second)
        self.assertEqual(second.count('NS8_MANAGED_FIELDS='), 1)
        self.assertEqual(policy.apply_smtp(second, 'custom'), env)

    def test_multiline_values_are_refused(self):
        with self.assertRaises(ValueError):
            policy.smtp_lines('smarthost', dict(SMARTHOST, password='a\nB=1'), HOST)

    def test_mode_file_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'smtp-mode.json')
            self.assertEqual(panel.read_smtp_mode(path), 'custom')
            panel.write_smtp_mode('smarthost', path)
            self.assertEqual(panel.read_smtp_mode(path), 'smarthost')
            Path(path).write_text('{"mode": "evil"}')
            self.assertEqual(panel.read_smtp_mode(path), 'custom')
            with self.assertRaises(ValueError):
                panel.write_smtp_mode('evil', path)

    def test_apply_smtp_mode_rewrites_the_environment_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'vaultwarden.env')
            Path(path).write_text('DOMAIN=https://vault\n')
            panel.apply_smtp_mode('smarthost', SMARTHOST, path, HOST)
            text = Path(path).read_text()
            self.assertIn('SMTP_HOST=smtp.example.org\n', text)
            self.assertEqual(oct(os.stat(path).st_mode & 0o777), '0o600')


class StaticTests(unittest.TestCase):
    def test_every_action_the_ui_runs_exists(self):
        actions = {p.name for p in (ROOT / 'imageroot/actions').iterdir()} | {'get-name'}
        used = set()
        for path in (ROOT / 'ui/src').rglob('*.vue'):
            used |= set(re.findall(r'runPanelTask\(\s*"([a-z-]+)"', path.read_text()))
        self.assertTrue(used)
        self.assertEqual(used - actions, set())

    def test_actions_have_executable_scripts_and_input_schemas(self):
        for name in ('query-panel-data', 'set-panel-settings', 'reset-panel-settings', 'manage-user',
                'manage-organization', 'test-smtp', 'set-smtp-mode'):
            directory = ROOT / 'imageroot/actions' / name
            script = directory / '20run'
            self.assertTrue(os.access(script, os.X_OK), name)
            self.assertEqual(json.loads((directory / 'validate-input.json').read_text())['type'], 'object')

    def test_panel_actions_are_not_open_to_readers(self):
        # NS8 lets cluster readers run actions starting with get-, read-, show- and list-;
        # these actions expose users, settings and the SMTP password
        for name in ('query-panel-data', 'set-panel-settings', 'reset-panel-settings', 'manage-user',
                'manage-organization', 'test-smtp', 'set-smtp-mode'):
            self.assertFalse(name.startswith(('get-', 'read-', 'show-', 'list-')), name)

    def test_translations_have_the_same_keys(self):
        def keys(value, prefix=''):
            if isinstance(value, dict):
                return {k for name, item in value.items() for k in keys(item, prefix + name + '.')}
            return {prefix}
        languages = {lang: json.loads((ROOT / f'ui/public/i18n/{lang}/translation.json').read_text()) for lang in ('en', 'de')}
        self.assertEqual(keys(languages['en']), keys(languages['de']))

    def test_runtime_patch_serves_the_page_data_and_managed_fields(self):
        patch = (ROOT / 'prototype/vaultwarden/deny-api-key-sso-only.patch').read_text()
        source = (ROOT / 'prototype/vaultwarden/ns8_admin.rs').read_text()
        for route in ('/ns8/data/settings', '/ns8/data/users', '/ns8/data/organizations', '/ns8/data/diagnostics'):
            self.assertIn(route, source)
        for handler in ('data_settings', 'data_users', 'data_organizations', 'data_diagnostics'):
            self.assertIn('ns8::' + handler, patch)
        self.assertIn('NS8_MANAGED_FIELDS', patch)

    def test_state_includes_the_mail_mode(self):
        self.assertIn('state/smtp-mode.json', (ROOT / 'imageroot/etc/state-include.conf').read_text())


if __name__ == '__main__':
    unittest.main()
