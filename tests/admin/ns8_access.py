#!/usr/bin/env python3
"""Run as root in an isolated NS8 test VM: two owners succeed, reader denied."""
import hashlib
import time
import http.cookiejar
import json
import secrets
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

module, host = sys.argv[1:]


def task(action, data=None, user=None, password=None, success=True):
    args = ['api-cli', 'run', action, '--data', json.dumps(data or {})]
    if user:
        # Bind the value to its option: token_urlsafe() can start with '-'.
        login = subprocess.run(['api-cli', 'login', '-u', user, f'--password={password}', '-o'], capture_output=True, text=True)
        assert login.returncode == 0, 'NS8 login failed (output hidden)'
        args += ['-t', login.stdout.strip()]
    result = subprocess.run(args, capture_output=True, text=True)
    if success:
        assert result.returncode == 0, f'{action} failed (output hidden)'
        return json.loads(result.stdout) if result.stdout.strip() else None
    assert result.returncode != 0, f'{action} unexpectedly authorized'


created = []
try:
    for index, role in enumerate(['owner', 'owner', 'reader']):
        username = 'vwtest' + secrets.token_hex(5)
        password = secrets.token_urlsafe(32)
        task('cluster/add-user', {'user': username,
            'password_hash': hashlib.sha256(password.encode()).hexdigest(),
            'set': {'display_name': 'Vaultwarden access test'},
            'grant': [{'role': role, 'on': '*'}]})
        created.append(username)
        if role == 'reader':
            task(f'module/{module}/get-configuration', user=username, password=password)
            task(f'module/{module}/open-admin', user=username, password=password, success=False)
            print('NS8 reader: admin access denied')
            continue
        login = task(f'module/{module}/open-admin', user=username, password=password)
        assert login['url'] == f'https://{host}/admin/'
        assert login['frame_ancestors'], 'No cluster manager origin allowed'
        assert 'token' not in login, 'Backend credential was exported'
        handle = secrets.token_urlsafe(32)
        jar = http.cookiejar.CookieJar()
        # QEMU uses a self-signed test certificate; production browser uses HTTPS normally.
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
            urllib.request.HTTPCookieProcessor(jar))
        def post(path, ticket, expected):
            request = urllib.request.Request('https://127.0.0.1/admin/' + path,
                data=urllib.parse.urlencode({'token': ticket + ':' + handle}).encode(),
                headers={'Host': host, 'Origin': login['frame_ancestors'][0]})
            try:
                with opener.open(request, timeout=20) as response:
                    assert response.status == expected, response.status
                    return response
            except urllib.error.HTTPError as error:
                assert error.code == expected, error.code
        response = post('', login['ticket'], 200)
        # The cluster manager on the node may embed the admin page.
        csp = response.headers['Content-Security-Policy']
        ancestors = csp.split('frame-ancestors', 1)[1].split(';', 1)[0].split()
        assert all(origin in ancestors for origin in login['frame_ancestors'])
        assert any(c.name == 'NS8_ADMIN' for c in jar)
        # A ticket works once; the module page renews with new ones
        post('', login['ticket'], 401)
        renewal = task(f'module/{module}/open-admin', user=username, password=password)
        post('ns8/renew', renewal['ticket'], 204)
        print('Admin ticket: single use, session renewed with a new ticket')
        with opener.open(urllib.request.Request('https://127.0.0.1/admin/diagnostics/config',
                headers={'Host': host}), timeout=20) as response:
            assert isinstance(json.load(response), dict)
        if index == 0:
            change = urllib.request.Request('https://127.0.0.1/admin/config',
                data=json.dumps({'password_hints_allowed': False,
                    'sso_enabled': False, 'admin_token': 'must-not-change',
                    'allowed_iframe_ancestors': ''}).encode(),
                headers={'Host': host, 'Content-Type': 'application/json'})
            with opener.open(change, timeout=20) as response:
                assert response.status == 200
            subprocess.run(['runagent', '-m', module, 'systemctl', '--user',
                'restart', 'vaultwarden.service'], check=True, capture_output=True)
            saved = subprocess.check_output(['runagent', '-m', module, 'podman',
                'exec', 'vaultwarden-app', 'cat', '/data/config.json'], text=True)
            values = json.loads(saved)
            assert values['password_hints_allowed'] is False
            assert values.get('admin_token') is None and values.get('sso_enabled') is None
            assert values.get('allowed_iframe_ancestors') is None
            print('Admin settings: saved and service restarted successfully')
        if index == 1:
            task('cluster/alter-user', {'user': username, 'set': {},
                'revoke': [{'role': 'owner', 'on': '*'}]})
            revoked = time.monotonic()
            task(f'module/{module}/open-admin', user=username, password=password, success=False)
            # Without new tickets the session ends within its lifetime
            while True:
                try:
                    opener.open(urllib.request.Request('https://127.0.0.1/admin/diagnostics/config',
                        headers={'Host': host}), timeout=20).close()
                except urllib.error.HTTPError as error:
                    assert error.code == 403, error.code
                    break
                assert time.monotonic() - revoked < login['session_seconds'] + 30, 'Admin session survived NS8 owner revocation'
                time.sleep(5)
            print('NS8 owner revocation: no new ticket, admin session ended within its lifetime')
        print('NS8 administrator: direct admin login successful')
    result = subprocess.run(['runagent', '-m', module, 'api-cli', 'run',
        f'module/{module}/open-admin', '--data', '{}'], capture_output=True)
    assert result.returncode != 0, 'Module unexpectedly obtained admin credentials'
    print('Module self-administration: admin login denied')
finally:
    for username in created:
        task('cluster/remove-user', {'user': username})
