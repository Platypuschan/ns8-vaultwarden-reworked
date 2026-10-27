"""Configuration policy shared by NS8 actions and integration tests."""
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
from urllib.parse import urlsplit


ADMIN_TOKEN = re.compile(r'[A-Za-z0-9_-]{43,128}\Z')
HOST = re.compile(r'(?=.{1,253}\Z)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\Z')
MODULE = re.compile(r'[a-z][a-z0-9-]*[1-9][0-9]*\Z')
ORIGINS = re.compile(r'(?:https://[a-z0-9.-]+(?: |\Z))*\Z')


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


def frame_ancestors(hostnames):
    """HTTPS origins allowed to embed Vaultwarden: the cluster manager runs on the nodes."""
    names = {h.rstrip('.').lower() for h in hostnames if isinstance(h, str)}
    return ' '.join(sorted('https://' + h for h in names if '.' in h and HOST.fullmatch(h)))


def environment(config, registration, admin_token, ancestors=''):
    issuer = registration['issuer']
    url = urlsplit(issuer)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path != '/realms/' + config['domain']):
        raise ValueError('Unexpected OIDC issuer')
    if not MODULE.fullmatch(registration['client_id']):
        raise ValueError('Invalid client ID')
    if not isinstance(admin_token, str) or not ADMIN_TOKEN.fullmatch(admin_token):
        raise ValueError('Invalid admin token')
    if not isinstance(ancestors, str) or not ORIGINS.fullmatch(ancestors):
        raise ValueError('Invalid frame ancestors')
    # Values go directly into a Podman env file, never through shell sourcing.
    values = {
        'DOMAIN': 'https://' + config['host'], 'NS8_MANAGED_CONFIG': 'true',
        'SSO_ENABLED': 'true', 'SSO_ONLY': 'true',
        'SSO_AUTHORITY': issuer, 'SSO_CLIENT_ID': registration['client_id'],
        'SSO_CLIENT_SECRET': registration['client_secret'],
        'SSO_SCOPES': 'profile email', 'SSO_PKCE': 'true',
        'SSO_AUTH_ONLY_NOT_SESSION': 'false', 'SIGNUPS_ALLOWED': 'false',
        'SSO_SIGNUPS_ALLOWED': 'true', 'SSO_SIGNUPS_MATCH_EMAIL': 'false',
        'SSO_ALLOW_UNKNOWN_EMAIL_VERIFICATION': 'false', 'INVITATIONS_ALLOWED': 'false',
        'EMAIL_CHANGE_ALLOWED': 'false', 'PUSH_ENABLED': 'false',
        'ROCKET_PORT': '80', 'IP_HEADER': 'X-Forwarded-For',
        'IP_HEADER_TRUSTED_PROXIES': 'local',
        # Used by automatic NS8-owner login and the local revocation timer.
        'ADMIN_TOKEN': admin_token,
        # Opening the module performs an automatic login. Leave room for
        # repeated visits and several NS8 admins behind the same address.
        'ADMIN_RATELIMIT_MAX_BURST': '30',
        # The admin page opens inside the cluster manager's application frame.
        'ALLOWED_IFRAME_ANCESTORS': ancestors,
    }
    if any(not isinstance(v, str) or any(c in v for c in '\r\n\x00') for v in values.values()):
        raise ValueError('Invalid multiline environment value')
    return ''.join(f'{k}={v}\n' for k, v in values.items())


def require_policy(config, state, require_binding=True):
    if require_binding and (state.get('policy_required') is not True or state.get('policy_group_pinned') is not True):
        raise ValueError('Update the IdP module first: required group protection is unavailable')
    if (state.get('enforced') is not True or state.get('enabled') is not True
            or state.get('group_path') != '/' + config['required_group']):
        raise ValueError('IdP group policy is missing, disabled or differs from required_group')


def admin_token(env_path='vaultwarden.env'):
    """Return the admin token of the environment file, or a new one."""
    try:
        with open(env_path) as f:
            for line in f:
                name, _, value = line.rstrip('\n').partition('=')
                if name == 'ADMIN_TOKEN' and ADMIN_TOKEN.fullmatch(value):
                    return value
    except FileNotFoundError:
        pass
    return secrets.token_urlsafe(48)


def env_value(name, env_path='vaultwarden.env'):
    with open(env_path) as f:
        for line in f:
            key, _, value = line.rstrip('\n').partition('=')
            if key == name:
                return value
    return None


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


def rotate_worker_token(env_path='vaultwarden.env'):
    """Invalidate the internal credential exported by pre-bridge releases."""
    with open(env_path) as stream:
        lines = [line for line in stream.read().splitlines() if not line.startswith('ADMIN_TOKEN=')]
    private_write(env_path, '\n'.join(lines + ['ADMIN_TOKEN=' + secrets.token_urlsafe(48)]) + '\n')
