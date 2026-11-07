"""Configuration policy shared by NS8 actions and integration tests."""
import json
import os
import pty
import select
import subprocess
import time
from pathlib import Path
import re
import secrets
import tempfile
from urllib.parse import urlsplit

from vaultwarden_admin import SESSION_SECONDS


ADMIN_TOKEN = re.compile(r'[A-Za-z0-9_-]{43,128}\Z')
# Argon2id PHC string as written by `vaultwarden hash`
ADMIN_TOKEN_HASH = re.compile(r'\$argon2id\$v=19\$m=[0-9]{1,8},t=[0-9]{1,3},p=[0-9]{1,3}\$[A-Za-z0-9+/]{16,}\$[A-Za-z0-9+/]{32,}\Z')
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
        process = subprocess.Popen(['podman', 'run', '--rm', '-t', '-i', '--pull=never', '--network=none',
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
    """Make a new worker credential: clear text to token_path, Argon2 hash
    returned for the ADMIN_TOKEN line. The hash is made first, so a failure
    leaves the previous pair untouched."""
    token = secrets.token_urlsafe(48)
    hashed = (hasher or (lambda t: argon2_hash(t, os.environ['VAULTWARDEN_REWORKED_SERVER_IMAGE'])))(token)
    if not ADMIN_TOKEN_HASH.fullmatch(hashed):
        raise ValueError('Invalid admin token hash')
    private_write(token_path, token + '\n')
    return hashed


def admin_token(env_path='vaultwarden.env', token_path=WORKER_TOKEN_FILE, hasher=None):
    """Return the ADMIN_TOKEN value of the environment file. It is kept only
    when it is an Argon2 hash with its clear-text worker file; a clear-text
    token (releases before the hash) or a half restored pair is replaced."""
    value = env_value('ADMIN_TOKEN', env_path) if os.path.exists(env_path) else None
    if value and ADMIN_TOKEN_HASH.fullmatch(value) and read_worker_token(token_path):
        return value
    return write_worker_credential(env_path, token_path, hasher)


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
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def rotate_worker_token(env_path='vaultwarden.env', token_path=WORKER_TOKEN_FILE, hasher=None):
    """Invalidate the internal credential of earlier releases and make a new
    hashed pair."""
    hashed = write_worker_credential(env_path, token_path, hasher)
    with open(env_path) as stream:
        lines = [line for line in stream.read().splitlines() if not line.startswith('ADMIN_TOKEN=')]
    private_write(env_path, '\n'.join(lines + ['ADMIN_TOKEN=' + hashed]) + '\n')
