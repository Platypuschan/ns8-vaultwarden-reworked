"""Configuration policy shared by NS8 actions and integration tests."""
import json
import os
import pty
import select
import subprocess
import time
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

from vaultwarden_admin import SESSION_SECONDS
from vaultwarden_credentials import (argon2_library, check_worker_credential,
    ensure_worker_credential, verify_worker_hash)


ADMIN_TOKEN = re.compile(r'[A-Za-z0-9_-]{43,128}\Z')
# Argon2id PHC string as written by `vaultwarden hash`
ADMIN_TOKEN_HASH = re.compile(r'\$argon2id\$v=19\$m=[0-9]{1,8},t=[0-9]{1,3},p=[0-9]{1,3}\$[A-Za-z0-9+/]{16,}\$[A-Za-z0-9+/]{32,}\Z')
# How Vaultwarden mail is configured: off, the cluster smarthost, or custom
SMTP_MODE_FILE = 'smtp-mode.json'
SMTP_MODES = ('disabled', 'smarthost', 'custom')
# SMTP environment lines of the module; all others are left untouched
SMTP_ENV_KEYS = ('_ENABLE_SMTP', 'USE_SENDMAIL', 'SMTP_HOST', 'SMTP_FROM', 'SMTP_SECURITY', 'SMTP_PORT',
    'SMTP_USERNAME', 'SMTP_PASSWORD', 'SMTP_ACCEPT_INVALID_CERTS', 'SMTP_ACCEPT_INVALID_HOSTNAMES',
    'NS8_MANAGED_FIELDS')
# Clear-text worker credential: only the revocation worker reads it
WORKER_TOKEN_FILE = 'admin-worker.token'
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
    if not isinstance(admin_token, str) or not (ADMIN_TOKEN.fullmatch(admin_token) or ADMIN_TOKEN_HASH.fullmatch(admin_token)):
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
        # Keep enrolled devices usable after the browser/IdP session ends.
        # AD access removal is enforced by vaultwarden-revoke.timer.
        'SSO_AUTH_ONLY_NOT_SESSION': 'true', 'SIGNUPS_ALLOWED': 'false',
        'SSO_SIGNUPS_ALLOWED': 'true', 'SSO_SIGNUPS_MATCH_EMAIL': 'false',
        'SSO_ALLOW_UNKNOWN_EMAIL_VERIFICATION': 'false', 'INVITATIONS_ALLOWED': 'false',
        'EMAIL_CHANGE_ALLOWED': 'false', 'PUSH_ENABLED': 'false',
        'ROCKET_PORT': '80', 'IP_HEADER': 'X-Forwarded-For',
        'IP_HEADER_TRUSTED_PROXIES': 'local',
        # Argon2id hash of the credential of the local revocation timer; the
        # clear text stays in WORKER_TOKEN_FILE. NS8 admins log in with
        # one-time tickets of open-admin.
        'ADMIN_TOKEN': admin_token,
        'NS8_ADMIN_SESSION_SECONDS': str(SESSION_SECONDS),
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
    if require_binding and 'policy_consumer_bound' not in state:
        raise ValueError('Update the IdP module first: required group protection is unavailable')
    if require_binding and any(state.get(field) is not True for field in
            ('policy_required', 'policy_group_pinned', 'policy_consumer_bound')):
        raise ValueError('IdP group policy is not bound to the configured group')
    enforced = state.get('enforced') is True or (not require_binding
        and state.get('enforced') is False and set(state.get('issues') or []) == {'expected_group_mismatch'})
    if (not enforced or state.get('enabled') is not True
            or state.get('group_path') != '/' + config['required_group']):
        raise ValueError('IdP group policy is missing, disabled or differs from required_group')


def argon2_hash(token, image, timeout=90):
    """Argon2id PHC string of token, made by `vaultwarden hash` of the runtime
    image. The command insists on a terminal; the token never appears in an
    argument list or in the environment."""
    if not ADMIN_TOKEN.fullmatch(token):
        raise ValueError('Invalid admin token')
    master, slave = pty.openpty()
    try:
        process = subprocess.Popen(['podman', 'run', '--rm', '-t', '-i', '--network=none',
            '--entrypoint', '/vaultwarden', image, 'hash', '--preset', 'owasp'],
            stdin=slave, stdout=slave, stderr=slave, close_fds=True)
    finally:
        os.close(slave)
    output, answered, deadline = b'', 0, time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 1)
            if ready:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output += chunk
                # "Password:" and "Confirm Password:"
                while answered < output.count(b'Password:') and answered < 2:
                    os.write(master, token.encode() + b'\n')
                    answered += 1
            elif process.poll() is not None:
                break
        else:
            raise RuntimeError('Hashing the admin token timed out')
    finally:
        os.close(master)
        if process.poll() is None:
            process.kill()
        process.wait()
    match = re.search(rb"ADMIN_TOKEN='([^']+)'", output)
    value = match.group(1).decode() if match else ''
    if process.returncode != 0 or not ADMIN_TOKEN_HASH.fullmatch(value):
        raise RuntimeError('Hashing the admin token failed')
    return value


def write_worker_credential(env_path='vaultwarden.env', token_path=WORKER_TOKEN_FILE, hasher=None):
    """Compatibility entry point for explicit rotation of the canonical record."""
    return ensure_worker_credential(env_path, token_path, hasher, rotate=True)


def admin_token(env_path='vaultwarden.env', token_path=WORKER_TOKEN_FILE, hasher=None):
    """Return the verified canonical hash, migrating/replaying state if needed."""
    return ensure_worker_credential(env_path, token_path, hasher)


def read_worker_token(token_path=WORKER_TOKEN_FILE):
    try:
        with open(token_path) as f:
            value = f.read().strip()
    except FileNotFoundError:
        return None
    return value if ADMIN_TOKEN.fullmatch(value) else None


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
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def rotate_worker_token(env_path='vaultwarden.env', token_path=WORKER_TOKEN_FILE, hasher=None):
    """Invalidate the internal credential of earlier releases and make a new
    hashed pair."""
    return ensure_worker_credential(env_path, token_path, hasher, rotate=True)


def smtp_sender(smarthost, host):
    """Default sender of the smarthost mode (Vaultwarden needs one with a host): the login if it
    is an address, else no-reply@ the module host. The module page can set another."""
    username = str(smarthost.get('username') or '')
    if re.fullmatch(r'[^@\s]+@[^@\s]+', username):
        return username
    return 'no-reply@' + host


def smtp_lines(mode, smarthost=None, host=None):
    """Environment lines of an SMTP mode. Vaultwarden shows the fields named
    in NS8_MANAGED_FIELDS as read-only and ignores saved values for them."""
    if mode == 'custom':
        return []
    if mode == 'smarthost':
        if not (smarthost and smarthost.get('enabled') and smarthost.get('host')):
            raise ValueError('The cluster has no smarthost configured')
        if not host or not HOST.fullmatch(host):
            raise ValueError('The module host is needed for the sender address')
        security = {'tls': 'force_tls', 'starttls': 'starttls'}.get(smarthost.get('encrypt_smtp'), 'off')
        verify = smarthost.get('tls_verify', True) is not False
        values = [('_ENABLE_SMTP', 'true'), ('USE_SENDMAIL', 'false'), ('SMTP_HOST', str(smarthost['host'])),
            ('SMTP_FROM', smtp_sender(smarthost, host)),
            ('SMTP_SECURITY', security), ('SMTP_PORT', str(int(smarthost.get('port') or 25))),
            ('SMTP_ACCEPT_INVALID_CERTS', 'false' if verify else 'true'),
            ('SMTP_ACCEPT_INVALID_HOSTNAMES', 'false' if verify else 'true')]
        if smarthost.get('username'):
            values.append(('SMTP_USERNAME', str(smarthost['username'])))
        if smarthost.get('password'):
            values.append(('SMTP_PASSWORD', str(smarthost['password'])))
        managed = ['_enable_smtp', 'use_sendmail', 'smtp_host', 'smtp_security', 'smtp_port', 'smtp_username',
            'smtp_password', 'smtp_accept_invalid_certs', 'smtp_accept_invalid_hostnames']
    elif mode == 'disabled':
        values = [('_ENABLE_SMTP', 'false'), ('USE_SENDMAIL', 'false')]
        managed = ['_enable_smtp', 'use_sendmail', 'smtp_host', 'smtp_security', 'smtp_port', 'smtp_from',
            'smtp_from_name', 'smtp_username', 'smtp_password', 'smtp_auth_mechanism', 'smtp_timeout', 'helo_name',
            'smtp_embed_images', 'smtp_accept_invalid_certs', 'smtp_accept_invalid_hostnames']
    else:
        raise ValueError('Invalid SMTP mode')
    values.append(('NS8_MANAGED_FIELDS', ','.join(managed)))
    if any(any(c in v for c in '\r\n\x00') for _, v in values):
        raise ValueError('Invalid multiline environment value')
    return [f'{k}={v}' for k, v in values]


def apply_smtp(env_text, mode, smarthost=None, host=None):
    """Environment text with the SMTP lines of mode instead of earlier ones."""
    lines = [line for line in env_text.splitlines() if line.partition('=')[0] not in SMTP_ENV_KEYS]
    return '\n'.join(lines + smtp_lines(mode, smarthost, host)) + '\n'
