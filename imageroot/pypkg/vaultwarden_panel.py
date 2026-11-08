"""Backend of the native NS8 pages that replace the Vaultwarden admin page.

The NS8 actions call the admin API of the Vaultwarden container on the
loopback port with the internal worker credential. Vaultwarden marks what
the module manages itself (SSO, domain, ...) as read-only; those fields
never reach the page.
"""
import json
import os
import re

import vaultwarden_config as policy
import vaultwarden_revoke as revoke

UUID = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z')
# Groups of the upstream settings page that the module page offers: General,
# Advanced, Global Duo, SMTP, Email 2FA. OpenID Connect is managed by the
# module and Yubikey is not offered.
SETTING_GROUPS = ('settings', 'advanced', 'duo', 'smtp', 'email_2fa')
SECTIONS = ('settings', 'users', 'organizations', 'diagnostics')
USER_OPERATIONS = {
    'delete': ('POST', 'delete'),
    'deauth': ('POST', 'deauth'),
    'disable': ('POST', 'disable'),
    'enable': ('POST', 'enable'),
    'remove-2fa': ('POST', 'remove-2fa'),
    'delete-sso': ('DELETE', 'sso'),
}
# Roles of an organization member in Vaultwarden
ORG_ROLES = {'owner': 0, 'admin': 1, 'user': 2, 'manager': 3}


def api(state_dir='.'):
    return revoke.AdminAPI('http://127.0.0.1:' + os.environ['TCP_PORT'], revoke.read_admin_token(), state_dir=state_dir)


def _quote(value):
    import urllib.parse
    return urllib.parse.quote(value, safe='')


def visible_settings(data):
    """The groups and fields the page shows: read-only fields are managed by
    the module (or by upstream) and stay hidden."""
    groups = []
    for group in data:
        if group.get('group') not in SETTING_GROUPS:
            continue
        elements = [{k: element[k] for k in ('name', 'value', 'default', 'type', 'doc', 'overridden')}
            for element in group['elements'] if element.get('editable')]
        # The group switch of upstream stays in the list as an ordinary field
        groups.append({'group': group['group'], 'title': group.get('groupdoc') or group['group'],
            'toggle': group.get('grouptoggle') or '', 'elements': elements})
    return groups


USER_FIELDS = ('id', 'name', 'email', 'emailVerified', 'twoFactorEnabled', '_status', 'cipher_count',
    'attachment_count', 'attachment_size', 'user_enabled', 'created_at', 'last_active', 'sso_identifier')
ORGANIZATION_FIELDS = ('id', 'name', 'billingEmail', 'user_count', 'cipher_count', 'collection_count',
    'group_count', 'event_count', 'attachment_count', 'attachment_size')


def slim_users(users):
    """Only what the page shows: the upstream records also hold the encrypted
    account keys and the security stamp, which must not reach the browser or
    the task log."""
    result = []
    for user in users:
        item = {name: user.get(name) for name in USER_FIELDS}
        item['organizations'] = [{'id': o.get('id'), 'name': o.get('name'), 'type': str(o.get('type'))}
            for o in user.get('organizations') or []]
        result.append(item)
    return result


def slim_organizations(organizations):
    return [{name: organization.get(name) for name in ORGANIZATION_FIELDS} for organization in organizations]


def get_data(section, connection=None):
    if section not in SECTIONS:
        raise ValueError('Unknown section')
    connection = connection or api()
    data = connection.request('GET', f'/admin/ns8/data/{section}')
    if section == 'settings':
        return visible_settings(data)
    if section == 'users':
        return slim_users(data)
    if section == 'organizations':
        return slim_organizations(data)
    return data


def clean_values(values, fields):
    """Check the submitted values against the editable fields; empty
    values become null, as on the upstream page."""
    if not isinstance(values, dict) or not values:
        raise ValueError('No settings to save')
    cleaned = {}
    for name, value in values.items():
        kind = fields.get(name)
        if kind is None:
            raise ValueError(f'Setting {name} cannot be changed here')
        if kind == 'checkbox':
            if not isinstance(value, bool):
                raise ValueError(f'Setting {name} must be true or false')
        elif kind == 'number':
            if value in ('', None):
                value = None
            elif isinstance(value, bool) or not isinstance(value, (int, str)) or not re.fullmatch(r'-?[0-9]{1,10}', str(value)):
                raise ValueError(f'Setting {name} must be a number')
            else:
                value = int(value)
        else:
            if value is not None and (not isinstance(value, str) or any(c in value for c in '\x00') or len(value) > 8192):
                raise ValueError(f'Setting {name} must be text')
            value = value or None
        cleaned[name] = value
    return cleaned


def merged_settings(raw, changes):
    """The complete user configuration after applying changes.

    Vaultwarden replaces its whole config.json on every save, so the result
    holds every editable value that differs from the default (also those of
    groups this page does not show, such as Yubikey). A cleared or default
    value is left out, which restores the default.
    """
    elements = {e['name']: e for g in raw for e in g['elements'] if e.get('editable')}
    shown = {e['name']: e['type'] for g in raw if g.get('group') in SETTING_GROUPS
        for e in g['elements'] if e.get('editable')}
    changes = clean_values(changes, shown)
    result = {name: e['value'] for name, e in elements.items()
        if e['value'] is not None and e['value'] != e['default']}
    for name, value in changes.items():
        if value is None or value == elements[name]['default']:
            result.pop(name, None)
        else:
            result[name] = value
    return result


def save_settings(values, connection=None):
    connection = connection or api()
    raw = connection.request('GET', '/admin/ns8/data/settings')
    connection.request('POST', '/admin/config', merged_settings(raw, values))


def reset_settings(connection=None):
    (connection or api()).request('POST', '/admin/config/delete')


def manage_user(operation, user_id=None, role=None, org_id=None, connection=None):
    connection = connection or api()
    if operation == 'resync-all':
        connection.request('POST', '/admin/users/update_revision')
        return
    if not isinstance(user_id, str) or not UUID.fullmatch(user_id):
        raise ValueError('Invalid user')
    if operation == 'set-org-role':
        if role not in ORG_ROLES or not isinstance(org_id, str) or not UUID.fullmatch(org_id):
            raise ValueError('Invalid organization role')
        connection.request('POST', '/admin/users/org_type',
            {'user_type': ORG_ROLES[role], 'user_uuid': user_id, 'org_uuid': org_id})
        return
    if operation not in USER_OPERATIONS:
        raise ValueError('Unknown user operation')
    method, suffix = USER_OPERATIONS[operation]
    connection.request(method, f'/admin/users/{_quote(user_id)}/{suffix}')


def delete_organization(org_id, connection=None):
    if not isinstance(org_id, str) or not UUID.fullmatch(org_id):
        raise ValueError('Invalid organization')
    (connection or api()).request('POST', f'/admin/organizations/{_quote(org_id)}/delete')


def test_smtp(email, connection=None):
    if not isinstance(email, str) or not re.fullmatch(r'[^@\s]{1,128}@[^@\s]{1,253}', email):
        raise ValueError('Invalid email address')
    (connection or api()).request('POST', '/admin/test/smtp', {'email': email})


#
# SMTP mode: Vaultwarden mail is off, follows the cluster smarthost, or is
# fully custom (the connection is then set on the module page).
#

def smarthost_available(smarthost):
    return bool(smarthost and smarthost.get('enabled') and smarthost.get('host'))


def read_smarthost():
    import agent
    return agent.get_smarthost_settings(agent.redis_connect(use_replica=True))


def read_smtp_mode(path=policy.SMTP_MODE_FILE):
    try:
        with open(path) as stream:
            mode = json.load(stream).get('mode')
    except (FileNotFoundError, ValueError, AttributeError):
        return 'custom'
    return mode if mode in policy.SMTP_MODES else 'custom'


def write_smtp_mode(mode, path=policy.SMTP_MODE_FILE):
    if mode not in policy.SMTP_MODES:
        raise ValueError('Invalid SMTP mode')
    policy.private_write(path, json.dumps({'mode': mode}))


def apply_smtp_mode(mode, smarthost=None, env_path='vaultwarden.env'):
    """Rewrite the SMTP lines of the environment file for mode."""
    with open(env_path) as stream:
        text = stream.read()
    policy.private_write(env_path, policy.apply_smtp(text, mode, smarthost))


def guarded(function, field='operation'):
    """Run an action body. Errors that the administrator can act on become
    NS8 validation errors; Vaultwarden messages carry no secrets."""
    import sys
    import agent
    try:
        return function()
    except (ValueError, revoke.RevokeError) as error:
        message = getattr(error, 'detail', '') or str(error)
        agent.set_status('validation-failed')
        json.dump([{'field': field, 'parameter': field, 'value': '', 'error': 'vaultwarden_error',
            'message': message}], sys.stdout)
        sys.exit(2)
