#!/usr/bin/env python3
"""The three SMTP modes against the real runtime: which fields it shows as read-only."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'imageroot/pypkg'))
import vaultwarden_config as policy

image = os.environ.get('VW_RUNTIME_IMAGE', 'localhost/vaultwarden-reworked-server:admin-ui')
SMARTHOST = {'enabled': True, 'host': 'smtp.example.org', 'port': 587, 'username': 'relay',
    'password': 'relay-secret', 'encrypt_smtp': 'starttls', 'tls_verify': True}


def settings(mode, smarthost, port):
    token = secrets.token_urlsafe(48)
    name = 'vw-smtp-mode-' + secrets.token_hex(4)
    with tempfile.TemporaryDirectory(prefix='vw-smtp-') as data:
        env = ['NS8_MANAGED_CONFIG=true', 'ADMIN_TOKEN=' + token, 'DOMAIN=https://vault.example.test',
            f'ROCKET_PORT={port}', 'ROCKET_ADDRESS=127.0.0.1', 'SSO_ENABLED=true', 'SSO_ONLY=true',
            'SSO_AUTHORITY=https://sso.example.test/realms/x', 'SSO_CLIENT_ID=f', 'SSO_CLIENT_SECRET=f',
            *policy.smtp_lines(mode, smarthost, 'vault.example.org')]
        args = ['podman', 'run', '-d', '--name', name, '--network=host', '-v', f'{data}:/data:Z']
        for line in env:
            args += ['-e', line]
        subprocess.run(args + [image], check=True, capture_output=True)
        try:
            for _ in range(60):
                try:
                    urllib.request.urlopen(f'http://127.0.0.1:{port}/alive', timeout=2).read()
                    break
                except OSError:
                    time.sleep(1)
            request = urllib.request.Request(f'http://127.0.0.1:{port}/admin/ns8/data/settings',
                headers={'X-NS8-Worker': token})
            groups = json.load(urllib.request.urlopen(request, timeout=20))
            return {e['name']: e for g in groups if g['group'] == 'smtp' for e in g['elements']}
        finally:
            subprocess.run(['podman', 'rm', '-f', name], capture_output=True)


def main():
    managed = settings('smarthost', SMARTHOST, 8391)
    for name in ('smtp_host', 'smtp_port', 'smtp_security', 'smtp_username', 'smtp_password'):
        assert not managed[name]['editable'], name + ' follows the smarthost'
    assert managed['smtp_host']['value'] == 'smtp.example.org' and managed['smtp_port']['value'] == 587
    assert managed['smtp_security']['value'] == 'starttls'
    assert managed['smtp_password']['value'] == '********', 'the smarthost password must not be shown'
    for name in ('smtp_from', 'smtp_from_name', 'smtp_timeout'):
        assert managed[name]['editable'], name + ' stays custom'
    assert managed['smtp_from']['value'] == 'relay@example.org' or managed['smtp_from']['value'] == 'no-reply@vault.example.org'
    print('SMTP mode smarthost: connection read-only, sender editable, password masked')

    off = settings('disabled', None, 8392)
    assert not any(e['editable'] for e in off.values()), 'with mail disabled nothing of the SMTP group is editable'
    assert off['_enable_smtp']['value'] is False
    print('SMTP mode disabled: mail off, group read-only')

    custom = settings('custom', None, 8393)
    for name in ('smtp_host', 'smtp_port', 'smtp_password', 'smtp_from'):
        assert custom[name]['editable'], name
    print('SMTP mode custom: everything editable')


main()
