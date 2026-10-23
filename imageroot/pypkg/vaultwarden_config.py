"""Configuration policy shared by NS8 actions and integration tests."""
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit


HOST = re.compile(r'(?=.{1,253}\Z)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\Z')
MODULE = re.compile(r'[a-z][a-z0-9-]*[1-9][0-9]*\Z')


def validate(data):
    for name in ('host', 'domain'):
        if not isinstance(data.get(name), str) or not HOST.fullmatch(data[name]):
            raise ValueError(f'Invalid {name}')
    if not isinstance(data.get('idp_module'), str) or not MODULE.fullmatch(data['idp_module']):
        raise ValueError('Invalid idp_module')
    group = data.get('required_group', 'services_vaultwarden')
    if not isinstance(group, str) or not re.fullmatch(r'[A-Za-z0-9_ .-]{1,128}', group):
        raise ValueError('Invalid required_group (direct group name only)')
    if not isinstance(data.get('lets_encrypt', True), bool):
        raise ValueError('lets_encrypt must be a boolean')
    return {k: data[k] for k in ('host', 'domain', 'idp_module')} | {
        'required_group': group, 'lets_encrypt': data.get('lets_encrypt', True)}


def environment(config, registration):
    issuer = registration['issuer']
    url = urlsplit(issuer)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path != '/realms/' + config['domain']):
        raise ValueError('Unexpected OIDC issuer')
    if not MODULE.fullmatch(registration['client_id']):
        raise ValueError('Invalid client ID')
    # Values go directly into a Podman env file, never through shell sourcing.
    values = {
        'DOMAIN': 'https://' + config['host'], 'SSO_ENABLED': 'true', 'SSO_ONLY': 'true',
        'SSO_AUTHORITY': issuer, 'SSO_CLIENT_ID': registration['client_id'],
        'SSO_CLIENT_SECRET': registration['client_secret'],
        'SSO_SCOPES': 'profile email', 'SSO_PKCE': 'true',
        'SSO_AUTH_ONLY_NOT_SESSION': 'false', 'SIGNUPS_ALLOWED': 'false',
        'SSO_SIGNUPS_ALLOWED': 'true', 'SSO_SIGNUPS_MATCH_EMAIL': 'false',
        'SSO_ALLOW_UNKNOWN_EMAIL_VERIFICATION': 'false', 'INVITATIONS_ALLOWED': 'false',
        'EMAIL_CHANGE_ALLOWED': 'false', 'PUSH_ENABLED': 'false',
        'ROCKET_PORT': '80', 'IP_HEADER': 'X-Forwarded-For',
        'IP_HEADER_TRUSTED_PROXIES': 'local',
    }
    if any(not isinstance(v, str) or any(c in v for c in '\r\n\x00') for v in values.values()):
        raise ValueError('Invalid multiline environment value')
    return ''.join(f'{k}={v}\n' for k, v in values.items())


def require_policy(config, state):
    if (state.get('enforced') is not True or state.get('enabled') is not True
            or state.get('group_path') != '/' + config['required_group']):
        raise ValueError('IdP group policy is missing, disabled or differs from required_group')


def private_write(path, text):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
