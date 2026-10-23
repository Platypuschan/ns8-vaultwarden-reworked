#!/usr/bin/env python3
"""Disposable Samba AD + ns8-idp Keycloak + Vaultwarden OIDC protocol tests.
Requires Podman. Only loopback ports are published; no production resources.
"""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import unittest
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'prototype/idp'))
import idpaccess


class Form(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.action = None
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form' and attrs.get('id') == 'kc-form-login':
            self.action = attrs['action']


def cmd(*args, check=True, **kwargs):
    return subprocess.run(args, check=check, capture_output=True, text=True, **kwargs)


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Admin:
    def __init__(self, url, password):
        self.url = url
        self.password = password
        self.token = None
    def request(self, method, path, data=None, params=None):
        if self.token is None:
            response = requests.post(self.url + '/realms/master/protocol/openid-connect/token', data={
                'grant_type': 'password', 'client_id': 'admin-cli', 'username': 'admin', 'password': self.password}, timeout=20)
            response.raise_for_status()
            self.token = response.json()['access_token']
        response = requests.request(method, self.url + '/admin/realms' + path, json=data,
            params=params, headers={'Authorization': 'Bearer ' + self.token}, timeout=25)
        if response.status_code == 401:
            self.token = None
            return self.request(method, path, data, params)
        if response.status_code >= 400:
            raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:400]}')
        return response.json() if response.content else response.headers.get('Location')
    def get(self, p, params=None): return self.request('GET', p, params=params)
    def post(self, p, data=None): return self.request('POST', p, data)
    def put(self, p, data=None): return self.request('PUT', p, data)
    def delete(self, p, data=None): return self.request('DELETE', p, data)
    def find_client(self, realm, cid):
        return next((c for c in self.get('/' + realm + '/clients', params={'clientId': cid}) if c['clientId'] == cid), None)


def wait_http(url, containers, seconds=180):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            if requests.get(url, timeout=2).status_code == 200:
                return
        except requests.RequestException:
            pass
        for name in containers:
            state = cmd('podman', 'inspect', '-f', '{{.State.Running}}', name)
            if state.stdout.strip() != 'true':
                logs = cmd('podman', 'logs', name).stdout + cmd('podman', 'logs', name).stderr
                raise RuntimeError(f'{name} exited: {logs[-5000:]}')
        time.sleep(2)
    raise TimeoutError(url)


class LoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suffix = secrets.token_hex(4)
        cls.network = 'vw-sso-' + cls.suffix
        cls.samba = 'vw-ad-' + cls.suffix
        cls.keycloak = 'vw-kc-' + cls.suffix
        cls.vaultwarden = 'vw-app-' + cls.suffix
        cls.names = []
        cls.password = secrets.token_urlsafe(24) + 'Aa1!'
        cls.kc_port, cls.vw_port = port(), port()
        cls.url = f'http://127.0.0.1:{cls.kc_port}'
        cls.vw_url = f'http://127.0.0.1:{cls.vw_port}'
        cls.addClassCleanup(cls.cleanup)
        cmd('podman', 'network', 'create', cls.network)
        env = dict(os.environ, AD_PASSWORD=cls.password)
        cmd('podman', 'run', '-d', '--name', cls.samba, '--hostname', 'dc.ad.test',
            '--network', cls.network, '--network-alias', 'samba', '--env', 'AD_PASSWORD',
            'localhost/ns8-vaultwarden-test-samba', env=env)
        cls.names.append(cls.samba)
        env = dict(os.environ, KC_BOOTSTRAP_ADMIN_USERNAME='admin', KC_BOOTSTRAP_ADMIN_PASSWORD=cls.password)
        cmd('podman', 'run', '-d', '--name', cls.keycloak, '--network', cls.network,
            '-p', f'127.0.0.1:{cls.kc_port}:8080', '--env', 'KC_BOOTSTRAP_ADMIN_USERNAME',
            '--env', 'KC_BOOTSTRAP_ADMIN_PASSWORD', 'localhost/ns8-idp-group-prototype',
            'start-dev', '--db=dev-file', '--features=scripts', '--hostname=' + cls.url,
            env=env)
        cls.names.append(cls.keycloak)
        wait_http(cls.url + '/realms/master/.well-known/openid-configuration', cls.names)
        cls.kc = Admin(cls.url, cls.password)
        cls.realm = 'ad.test'
        cls.kc.post('', {'realm': cls.realm, 'enabled': True, 'sslRequired': 'none',
            'registrationAllowed': False, 'accessTokenLifespan': 600})
        rid = cls.kc.get('/ad.test')['id']
        # Same read-only AD LDAP schema and group mapper as ns8-idp, using the
        # private test network in place of the NS8 ldapproxy.
        conf = {k: [v] for k,v in {
            'enabled':'true', 'editMode':'READ_ONLY', 'connectionUrl':'ldap://samba:389',
            'authType':'simple', 'bindDn':'CN=Administrator,CN=Users,DC=ad,DC=test',
            'bindCredential':cls.password, 'importEnabled':'true', 'syncRegistrations':'false',
            'trustEmail':'true', 'vendor':'ad', 'usersDn':'DC=ad,DC=test',
            'searchScope':'2', 'usernameLDAPAttribute':'sAMAccountName', 'rdnLDAPAttribute':'cn',
            'uuidLDAPAttribute':'objectGUID', 'userObjectClasses':'person, organizationalPerson, user',
            'customUserSearchFilter':'(&(objectCategory=person)(!(sAMAccountName=Administrator)))',
            'pagination':'true', 'cachePolicy':'DEFAULT', 'connectionTimeout':'3000', 'readTimeout':'3000'
        }.items()}
        cls.kc.post('/ad.test/components', {'name':'ns8-ldap','providerId':'ldap',
            'providerType':'org.keycloak.storage.UserStorageProvider','parentId':rid,'config':conf})
        cls.component = cls.kc.get('/ad.test/components',params={'type':'org.keycloak.storage.UserStorageProvider'})[0]
        cls.kc.post('/ad.test/components', {'name':'groups','providerId':'group-ldap-mapper',
            'providerType':'org.keycloak.storage.ldap.mappers.LDAPStorageMapper',
            'parentId':cls.component['id'], 'config':{k:[v] for k,v in {
                'group.name.ldap.attribute':'cn', 'groups.dn':'DC=ad,DC=test',
                'group.object.classes':'group', 'preserve.group.inheritance':'false',
                'membership.ldap.attribute':'member', 'membership.attribute.type':'DN',
                'membership.user.ldap.attribute':'cn', 'mode':'READ_ONLY',
                'user.roles.retrieve.strategy':'LOAD_GROUPS_BY_MEMBER_ATTRIBUTE',
                'drop.non.existing.groups.during.sync':'false'
            }.items()}})
        mapper = next(c for c in cls.kc.get('/ad.test/components',params={'parent':cls.component['id']}) if c['name']=='groups')
        # Wait for domain provisioning, then import group objects once. Membership
        # itself is looked up on authentication, never maintained in this runner.
        end = time.monotonic()+90
        while True:
            try:
                cls.kc.post('/ad.test/user-storage/' + cls.component['id'] + '/mappers/' + mapper['id'] + '/sync?direction=fedToKeycloak')
                break
            except RuntimeError:
                if time.monotonic()>end: raise
                time.sleep(2)
        cls.secret = secrets.token_urlsafe(32)
        for cid in ('vaultwarden1','other1'):
            cls.kc.post('/ad.test/clients', {'clientId':cid,'protocol':'openid-connect',
                'enabled':True,'publicClient':False,'secret':cls.secret,
                'standardFlowEnabled':True,'directAccessGrantsEnabled':False,
                'redirectUris':[cls.vw_url+'/identity/connect/oidc-signin'],
                'attributes':{'ns8.module_id':cid}, 'defaultClientScopes':['profile','email']})
        cls.policy = idpaccess.apply(cls.kc, 'ad.test', 'vaultwarden1', '/services_vaultwarden')
        env = dict(os.environ, DOMAIN=cls.vw_url, SSO_ENABLED='true', SSO_ONLY='true',
            SSO_AUTHORITY=cls.url+'/realms/ad.test', SSO_CLIENT_ID='vaultwarden1',
            SSO_CLIENT_SECRET=cls.secret, SSO_SCOPES='profile email', SSO_PKCE='true',
            SIGNUPS_ALLOWED='false', SSO_SIGNUPS_ALLOWED='true', SSO_SIGNUPS_MATCH_EMAIL='false',
            SSO_ALLOW_UNKNOWN_EMAIL_VERIFICATION='false', ROCKET_PORT='80')
        # OIDC discovery/token calls from the container must reach the exact
        # loopback issuer. Sharing the host network is confined to this test.
        args = ['podman','run','-d','--name',cls.vaultwarden,'--network','host']
        env['ROCKET_PORT']=str(cls.vw_port)
        env['ROCKET_ADDRESS']='127.0.0.1'
        for key in ('DOMAIN','SSO_ENABLED','SSO_ONLY','SSO_AUTHORITY','SSO_CLIENT_ID','SSO_CLIENT_SECRET',
                'SSO_SCOPES','SSO_PKCE','SIGNUPS_ALLOWED','SSO_SIGNUPS_ALLOWED','SSO_SIGNUPS_MATCH_EMAIL',
                'SSO_ALLOW_UNKNOWN_EMAIL_VERIFICATION','ROCKET_PORT','ROCKET_ADDRESS'):
            args += ['--env',key]
        args += ['--volume',f'vw-data-{cls.suffix}:/data','docker.io/vaultwarden/server:1.37.2']
        cmd(*args,env=env)
        cls.names.append(cls.vaultwarden)
        wait_http(cls.vw_url+'/alive',cls.names)

    @classmethod
    def cleanup(cls):
        out=ROOT/'tests/outputs/integration'
        out.mkdir(parents=True,exist_ok=True)
        for name in reversed(cls.names):
            logs=cmd('podman','logs',name,check=False)
            # Never retain passwords, authorization URLs/codes or tokens.
            lines=[l for l in (logs.stdout+logs.stderr).splitlines()
                if not any(v in l.lower() for v in ('password','token','code=','state=','bindcredential','secret'))]
            (out/(name.split('-')[1]+'.log')).write_text('\n'.join(lines))
            cmd('podman','rm','-f',name,check=False)
        cmd('podman','volume','rm',f'vw-data-{cls.suffix}',check=False)
        cmd('podman','network','rm',cls.network,check=False)

    def auth(self, username, session=None, client='vaultwarden1', mobile=False):
        s=session or requests.Session()
        verifier=secrets.token_urlsafe(48)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        if mobile:
            url=self.vw_url+'/identity/connect/authorize?'+urlencode({
                'client_id':'mobile','redirect_uri':'bitwarden://sso-callback','response_type':'code',
                'scope':'api offline_access','state':secrets.token_urlsafe(24),
                'code_challenge':challenge,'code_challenge_method':'S256'})
        else:
            url=self.url+'/realms/ad.test/protocol/openid-connect/auth?'+urlencode({
                'client_id':client,'redirect_uri':self.vw_url+'/identity/connect/oidc-signin',
                'response_type':'code','scope':'openid profile email','state':secrets.token_urlsafe(24),
                'code_challenge':challenge,'code_challenge_method':'S256'})
        r=s.get(url,allow_redirects=False,timeout=20)
        for _ in range(20):
            # Keycloak treats loopback as a secure browser context and sets
            # Secure cookies even on HTTP. requests lacks that browser exception.
            # Only our ephemeral loopback fixture is allowed to relax this flag.
            for cookie in s.cookies:
                if cookie.domain == '127.0.0.1': cookie.secure = False
            if r.is_redirect:
                target=urljoin(r.url,r.headers['Location'])
                if target.startswith('bitwarden:') or (not mobile and target.startswith(self.vw_url)):
                    return s,r,target,verifier
                r=s.get(target,allow_redirects=False,timeout=20)
                continue
            form=Form(r.text)
            if form.action:
                r=s.post(form.action,data={'username':username,'password':self.password},allow_redirects=False,timeout=20)
                continue
            return s,r,None,verifier
        self.fail('Redirect loop')

    def test_01_allowed_and_denied(self):
        self.assertTrue(self.policy['enforced'])
        for username,expected in [('allowed',True),('denied',False)]:
            with self.subTest(username=username):
                _,r,target,_=self.auth(username)
                self.assertEqual(bool(target and 'code=' in target),expected,
                    f'{username}: HTTP {r.status_code}, page {r.text[-1000:]}')

    def test_02_other_client_unrestricted(self):
        _,_,target,_=self.auth('denied',client='other1')
        self.assertIn('code=',target or '')

    def test_03_mobile_protocol_and_password_bypass(self):
        s,r,target,verifier=self.auth('allowed',mobile=True)
        self.assertTrue(target and target.startswith('bitwarden://sso-callback'),f'HTTP {r.status_code}: {r.text[:200]}')
        code=parse_qs(urlsplit(target).query)['code'][0]
        response=requests.post(self.vw_url+'/identity/connect/token',data={
            'grant_type':'authorization_code','client_id':'mobile','scope':'api offline_access','code':code,'code_verifier':verifier,
            'redirect_uri':'bitwarden://sso-callback','deviceIdentifier':secrets.token_hex(16),
            'deviceName':'Protocol test Android','deviceType':'0'},timeout=20)
        self.assertEqual(response.status_code,200,response.text[:300])
        self.assertIn('access_token',response.json())
        # This is a new-device OIDC authentication, not biometric UI testing.
        response=requests.post(self.vw_url+'/identity/connect/token',data={
            'grant_type':'password','client_id':'mobile','scope':'api offline_access','username':'allowed@example.test',
            'password':'irrelevant','deviceIdentifier':secrets.token_hex(16),
            'deviceName':'Bypass test','deviceType':'0'},timeout=20)
        self.assertNotEqual(response.status_code,200)
        self.assertNotIn('access_token',response.json())

    def test_04_revocation_with_cookie_and_new_device(self):
        session,_,target,_=self.auth('allowed',client='other1')
        self.assertIn('code=',target or '')
        cmd('podman','exec',self.samba,'samba-tool','group','removemembers','services_vaultwarden','allowed')
        try:
            for label,s,mobile in [('existing cookie',session,False),('new device',None,True)]:
                with self.subTest(label=label):
                    _,r,target,_=self.auth('allowed',session=s,mobile=mobile)
                    self.assertIsNone(target,f'{label}: got a callback after revocation')
                    self.assertEqual(r.status_code,403)
            # Login to other applications still succeeds after removal.
            _,_,target,_=self.auth('allowed',session=session,client='other1')
            self.assertIn('code=',target or '')
        finally:
            cmd('podman','exec',self.samba,'samba-tool','group','addmembers','services_vaultwarden','allowed')
        _,_,target,_=self.auth('allowed')
        self.assertIn('code=',target or '')

    def test_05_missing_policy_denies(self):
        client=self.kc.find_client('ad.test','vaultwarden1')
        attrs=dict(client['attributes'])
        client['attributes'][idpaccess.GROUP_ID] = ''
        self.kc.put('/ad.test/clients/'+client['id'],client)
        try:
            _,r,target,_=self.auth('allowed')
            self.assertIsNone(target)
            self.assertEqual(r.status_code,403)
        finally:
            client['attributes']=attrs
            self.kc.put('/ad.test/clients/'+client['id'],client)

    def test_06_policy_idempotent_and_restart_persistent(self):
        state=idpaccess.apply(self.kc,'ad.test','vaultwarden1','/services_vaultwarden')
        self.assertTrue(state['enforced'])
        cmd('podman','restart',self.keycloak)
        wait_http(self.url+'/realms/ad.test/.well-known/openid-configuration',self.names)
        self.kc.token=None
        _,_,target,_=self.auth('allowed')
        self.assertIn('code=',target or '')
        _,r,target,_=self.auth('denied')
        self.assertIsNone(target)
        self.assertEqual(r.status_code,403)
        cmd('podman','restart',self.vaultwarden)
        wait_http(self.vw_url+'/alive',self.names)
        # The first mobile login's existing account must still authenticate.
        _,r,target,verifier=self.auth('allowed',mobile=True)
        self.assertTrue(target and target.startswith('bitwarden://sso-callback'))

    def test_07_directory_unavailable_denies(self):
        session,_,target,_=self.auth('allowed',client='other1')
        self.assertIn('code=',target or '')
        cmd('podman','pause',self.samba)
        try:
            _,r,target,_=self.auth('allowed',session=session)
            self.assertIsNone(target)
            self.assertGreaterEqual(r.status_code,400)
        finally:
            cmd('podman','unpause',self.samba)

    def test_08_code_and_refresh_cannot_bypass_revocation(self):
        _,_,target,verifier=self.auth('allowed')
        self.assertIn('code=',target or '')
        # Issue one live refresh token before removing group membership.
        _,_,second,second_verifier=self.auth('allowed')
        token_url=self.url+'/realms/ad.test/protocol/openid-connect/token'
        def redeem(callback, pkce):
            return requests.post(token_url,data={
                'grant_type':'authorization_code','client_id':'vaultwarden1',
                'client_secret':self.secret,'code':parse_qs(urlsplit(callback).query)['code'][0],
                'redirect_uri':self.vw_url+'/identity/connect/oidc-signin','code_verifier':pkce},timeout=20)
        live=redeem(second,second_verifier)
        self.assertEqual(live.status_code,200)
        refresh=live.json()['refresh_token']
        cmd('podman','exec',self.samba,'samba-tool','group','removemembers','services_vaultwarden','allowed')
        try:
            stale=redeem(target,verifier)
            self.assertEqual(stale.status_code,403)
            self.assertNotIn('access_token',stale.json())
            refreshed=requests.post(token_url,data={
                'grant_type':'refresh_token','client_id':'vaultwarden1',
                'client_secret':self.secret,'refresh_token':refresh},timeout=20)
            self.assertEqual(refreshed.status_code,403)
            self.assertNotIn('access_token',refreshed.json())
        finally:
            cmd('podman','exec',self.samba,'samba-tool','group','addmembers','services_vaultwarden','allowed')

    def test_09_unsafe_ldap_cache_denies(self):
        comp=self.kc.get('/ad.test/components/'+self.component['id'])
        original=dict(comp['config'])
        comp['config']['cachePolicy']=['DEFAULT']
        self.kc.put('/ad.test/components/'+comp['id'],comp)
        try:
            _,r,target,_=self.auth('allowed')
            self.assertIsNone(target)
            self.assertEqual(r.status_code,403)
            client=self.kc.find_client('ad.test','vaultwarden1')
            self.assertFalse(idpaccess.access_state(self.kc,'ad.test',client)['enforced'])
        finally:
            comp['config']=original
            self.kc.put('/ad.test/components/'+comp['id'],comp)
            self.kc.post('/ad.test/clear-user-cache')


if __name__=='__main__':
    unittest.main(verbosity=2)
