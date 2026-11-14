"""Canonical, crash-recoverable worker credentials. Call ensure under configuration lock."""
import ctypes
import ctypes.util
import json
import os
from pathlib import Path
import re
import secrets

CREDENTIAL_SCHEMA = 1
CREDENTIAL_FILE = 'worker-credential.json'


def argon2_library():
    """Stable C ABI, independent of the agent's Python version."""
    bundled = Path(__file__).resolve().parent.parent / 'lib' / 'libargon2.so.1'
    library = str(bundled) if bundled.exists() else (ctypes.util.find_library('argon2') or 'libargon2.so.1')
    return ctypes.CDLL(library)


def verify_worker_hash(token, hashed):
    """Real Argon2id verification; no subprocess, argv, env or secret diagnostics."""
    from vaultwarden_config import ADMIN_TOKEN, ADMIN_TOKEN_HASH
    if not isinstance(token, str) or not ADMIN_TOKEN.fullmatch(token):
        return False
    if not isinstance(hashed, str) or not ADMIN_TOKEN_HASH.fullmatch(hashed):
        return False
    memory, iterations, lanes = map(int, re.search(r'm=(\d+),t=(\d+),p=(\d+)', hashed).groups())
    # Bound untrusted PHC costs before calling native code.
    if not (8 <= memory <= 131072 and 1 <= iterations <= 10 and 1 <= lanes <= 16):
        return False
    library = argon2_library()
    library.argon2id_verify.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t]
    library.argon2id_verify.restype = ctypes.c_int
    secret = token.encode()
    return library.argon2id_verify(hashed.encode(), secret, len(secret)) == 0


def credential_path(token_path):
    return Path(token_path).with_name(CREDENTIAL_FILE)


def read_credential(token_path):
    path = credential_path(token_path)
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (ValueError, OSError):
        raise ValueError('Invalid worker credential record') from None
    if (not isinstance(data, dict) or type(data.get('schema')) is not int
            or data['schema'] not in (0, CREDENTIAL_SCHEMA)
            or not verify_worker_hash(data.get('token'), data.get('hash'))):
        raise ValueError('Invalid worker credential record')
    if path.stat().st_mode & 0o777 != 0o600:
        raise ValueError('Worker credential record must be private (0600)')
    return data


def env_hash(env_path):
    if not Path(env_path).exists():
        return None
    values = [line.partition('=')[2] for line in Path(env_path).read_text().splitlines()
              if line.startswith('ADMIN_TOKEN=')]
    if len(values) > 1:
        raise ValueError('Duplicate worker credential in environment')
    return values[0] if values else None


def check_worker_credential(env_path='vaultwarden.env', token_path='admin-worker.token'):
    """Read-only start gate. Recovery is a separate locked lifecycle action."""
    data = read_credential(token_path)
    if (data is None or data['schema'] != CREDENTIAL_SCHEMA
            or env_hash(env_path) != data['hash']):
        raise ValueError('Worker credentials are incoherent; run credential recovery')
    if Path(env_path).stat().st_mode & 0o777 != 0o600:
        raise ValueError('Worker environment must be private (0600)')
    return data['token']


def ensure_worker_credential(env_path='vaultwarden.env', token_path='admin-worker.token',
                             hasher=None, rotate=False):
    """Commit canonical record BEFORE projection; replay interrupted projection.

    Valid legacy pairs migrate without changing either credential. Hash-only
    or mismatched legacy state requires explicit rotation, never silent update
    rotation. Cleartext legacy environment and token-only state are migratable.
    """
    from vaultwarden_config import ADMIN_TOKEN, ADMIN_TOKEN_HASH, argon2_hash, private_write, read_worker_token
    data = read_credential(token_path)
    value = env_hash(env_path)
    if data is None or rotate or data['schema'] != CREDENTIAL_SCHEMA:
        token, hashed = None, None
        if not rotate and data is None:
            legacy = read_worker_token(token_path)
            if value and ADMIN_TOKEN_HASH.fullmatch(value):
                if not legacy or not verify_worker_hash(legacy, value):
                    raise ValueError('Legacy worker credentials are incoherent')
                token, hashed = legacy, value
            elif value and ADMIN_TOKEN.fullmatch(value):
                token = value
            elif value is not None:
                raise ValueError('Invalid legacy worker credential')
            else:
                token = legacy
        if token is None:
            token = secrets.token_urlsafe(48)
        if hashed is None:
            hashed = (hasher or (lambda t: argon2_hash(t,
                os.environ['VAULTWARDEN_REWORKED_SERVER_IMAGE'])))(token)
        if not verify_worker_hash(token, hashed):
            raise ValueError('Generated worker credential does not match its hash')
        data = {'schema': CREDENTIAL_SCHEMA, 'token': token, 'hash': hashed}
        private_write(credential_path(token_path), json.dumps(data) + '\n')
    if Path(env_path).exists():
        lines = [line for line in Path(env_path).read_text().splitlines()
                 if not line.startswith('ADMIN_TOKEN=')]
        if value != data['hash'] or Path(env_path).stat().st_mode & 0o777 != 0o600:
            private_write(env_path, '\n'.join(lines + ['ADMIN_TOKEN=' + data['hash']]) + '\n')
    # Old backups remain readable; new backups use only the canonical record.
    Path(token_path).unlink(missing_ok=True)
    return data['hash']
