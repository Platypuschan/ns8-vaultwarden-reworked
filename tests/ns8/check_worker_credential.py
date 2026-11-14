#!/usr/bin/env python3
"""Destructive negative test ONLY in the disposable QEMU module fixture.

All secret comparisons happen in-process; stdout/stderr from child commands
are suppressed. Always recover the projection and restart the fixture.
"""
from pathlib import Path
import subprocess
import sys

import agent
import vaultwarden_config as policy
import vaultwarden_revoke as revoke


def systemctl(*args):
    return subprocess.run(['systemctl', '--user', *args],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode


def main():
    before = Path('worker-credential.json').read_bytes()
    systemctl('stop', 'vaultwarden-revoke.timer', 'vaultwarden-revoke.service')
    try:
        with agent.exclusive_file_lock('configuration'):
            # Valid-looking PHC for another credential is still incoherent.
            replacement = policy.argon2_hash('x' * 64, __import__('os').environ['VAULTWARDEN_REWORKED_SERVER_IMAGE'])
            text = Path('vaultwarden.env').read_text()
            lines = [line for line in text.splitlines() if not line.startswith('ADMIN_TOKEN=')]
            policy.private_write('vaultwarden.env', '\n'.join(lines + ['ADMIN_TOKEN=' + replacement]) + '\n')
        try:
            revoke.read_admin_token()
        except revoke.RevokeError:
            pass
        else:
            raise AssertionError('Worker accepted incoherent credentials')
        assert systemctl('restart', 'vaultwarden.service') != 0, 'Service accepted incoherent credentials'
        assert systemctl('is-active', '--quiet', 'vaultwarden.service') != 0
    finally:
        with agent.exclusive_file_lock('configuration'):
            policy.ensure_worker_credential()
            policy.check_worker_credential()
        assert Path('worker-credential.json').read_bytes() == before
        systemctl('reset-failed', 'vaultwarden.service')
        assert systemctl('start', 'vaultwarden.service') == 0
        assert systemctl('start', 'vaultwarden-revoke.timer') == 0


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Credential fail-closed fixture failed', file=sys.stderr)
        sys.exit(1)
    print('Credential fail-closed fixture passed')
