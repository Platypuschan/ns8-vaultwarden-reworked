"""Revocation of Vaultwarden accounts whose users left the AD group.

The IdP denies new logins and token refreshes to users outside the
group, but an existing Vaultwarden session lasts until its IdP access
token expires. The revoke-access timer closes that gap: it disables the
Vaultwarden account of every user that is no longer a direct, enabled
member of the group, which logs out all its devices, and enables it
again when the user is a member again. Accounts are matched by e-mail
address, the AD mail attribute.

Only accounts disabled by the timer are enabled again: an account that
an administrator disabled stays disabled. Offline copies of a vault on
the devices are not erased: the Bitwarden clients delete them only when
they connect and are logged out.
"""
import ipaddress
import json
import os
import urllib.error
import urllib.parse
import urllib.request

LDAP_BITWISE_AND = '1.2.840.113556.1.4.803'
ACCOUNTDISABLE = 2
REVOKED_FILE = 'revoked-users.json'
SESSION_FILE = 'admin-session'


class RevokeError(Exception):
    """A safe-to-show error; never contains a password or a token."""


#
# AD group members
#

def domain_settings(domain_name):
    from agent.ldapproxy import Ldapproxy
    proxy = Ldapproxy()
    domain = proxy.get_domain(domain_name)
    if domain is None:
        raise RevokeError(f'The user domain {domain_name!r} is not available')
    if domain.get('schema') != 'ad':
        raise RevokeError(f'The user domain {domain_name!r} is not an Active Directory')
    host = str(domain.get('host', ''))
    # The NS8 LDAP proxy listens on the node itself; never send the bind
    # credentials anywhere else
    try:
        loopback = host == 'localhost' or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        raise RevokeError('NS8 returned a non-loopback LDAP proxy endpoint')
    return {
        'host': host, 'port': int(domain['port']), 'base_dn': str(domain['base_dn']),
        'bind_dn': str(domain['bind_dn']), 'bind_password': str(domain['bind_password']),
        'hidden_users_clause': proxy.get_ldap_users_search_filter_clause(domain_name),
    }


def escape_filter_chars(value):
    """Escape a value for an LDAP search filter, as RFC 4515."""
    return ''.join('\\%02x' % ord(c) if c in '\\*()\0' else c for c in value)


def members_filter(group_dn, hidden_users_clause=''):
    # Direct members only, like the IdP check; disabled AD accounts are
    # not members
    return ''.join(['(&(objectCategory=person)(objectClass=user)',
        f'(memberOf={escape_filter_chars(group_dn)})',
        f'(!(userAccountControl:{LDAP_BITWISE_AND}:={ACCOUNTDISABLE}))',
        hidden_users_clause, ')'])


def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if len(value) == 1 else None
    return value


def group_member_mails(settings, group):
    """Return the lower-case mail addresses of the enabled direct members
    of an AD group. Raise RevokeError if the group cannot be read, so a
    failed lookup is never taken for an empty group."""
    from ldap3 import NONE, SUBTREE, Connection, Server
    try:
        server = Server(settings['host'], port=settings['port'], connect_timeout=10, get_info=NONE)
        connection = Connection(server, user=settings['bind_dn'], password=settings['bind_password'],
            auto_bind=True, receive_timeout=30, raise_exceptions=True)
    except Exception as error:
        raise RevokeError(f'Cannot connect to the user domain: {type(error).__name__}') from None
    try:
        connection.search(search_base=settings['base_dn'],
            search_filter=f'(&(objectCategory=group)(sAMAccountName={escape_filter_chars(group)}))',
            search_scope=SUBTREE, attributes=['distinguishedName'], size_limit=2)
        if len(connection.entries) != 1:
            raise RevokeError(f'The AD group {group!r} was not found exactly once')
        group_dn = str(connection.entries[0].entry_dn)
        results = connection.extend.standard.paged_search(search_base=settings['base_dn'],
            search_filter=members_filter(group_dn, settings['hidden_users_clause']),
            search_scope=SUBTREE, attributes=['mail'], paged_size=500, generator=False)
        mails = set()
        for entry in results:
            if entry.get('type') == 'searchResEntry':
                mail = _first(entry.get('attributes', {}).get('mail'))
                if mail:
                    mails.add(str(mail).strip().lower())
        return mails
    except RevokeError:
        raise
    except Exception as error:
        raise RevokeError(f'Reading the AD group {group!r} failed: {type(error).__name__}') from None
    finally:
        connection.unbind()


#
# Vaultwarden admin API, on the loopback port of the container
#

class AdminAPI:
    """Client of the Vaultwarden admin API. The admin session cookie is
    kept in a file: Vaultwarden limits admin logins to a few per five
    minutes."""
    def __init__(self, base_url, token, state_dir='.'):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.session_path = os.path.join(state_dir, SESSION_FILE)
        try:
            with open(self.session_path) as f:
                self.cookie = f.read().strip() or None
        except FileNotFoundError:
            self.cookie = None

    def _open(self, method, path, body=None, headers=None):
        request = urllib.request.Request(self.base_url + path, data=body, method=method, headers=headers or {})
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            with opener.open(request, timeout=30) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read()
        except (urllib.error.URLError, OSError) as error:
            raise RevokeError(f'Vaultwarden is not reachable: {type(error).__name__}') from None

    def login(self):
        body = urllib.parse.urlencode({'token': self.token}).encode()
        status, headers, _ = self._open('POST', '/admin', body,
            {'Content-Type': 'application/x-www-form-urlencoded'})
        cookie = None
        for header in headers.get_all('Set-Cookie') or []:
            name, _, rest = header.partition('=')
            if name.strip() == 'VW_ADMIN':
                cookie = rest.split(';', 1)[0]
        if status not in (200, 303) or not cookie:
            raise RevokeError(f'Vaultwarden admin login failed: HTTP {status}')
        self.cookie = cookie
        fd = os.open(self.session_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(cookie)

    def request(self, method, path):
        for attempt in (1, 2):
            if not self.cookie:
                self.login()
            headers = {'Cookie': 'VW_ADMIN=' + self.cookie}
            body = None
            if method == 'POST':
                headers['Content-Type'] = 'application/json'
                body = b''
            status, _, data = self._open(method, path, body, headers)
            if status in (401, 403, 303) and attempt == 1:
                # The admin session expired
                self.cookie = None
                continue
            if status >= 300:
                raise RevokeError(f'Vaultwarden admin API {method} {path.split("/")[1]}: HTTP {status}')
            return json.loads(data) if data else None

    def users(self):
        return self.request('GET', '/admin/users')

    def disable(self, user_id):
        self.request('POST', f'/admin/users/{urllib.parse.quote(user_id)}/disable')

    def enable(self, user_id):
        self.request('POST', f'/admin/users/{urllib.parse.quote(user_id)}/enable')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


#
# Revocation
#

def _load_revoked(state_dir):
    try:
        with open(os.path.join(state_dir, REVOKED_FILE)) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _save_revoked(state_dir, revoked):
    path = os.path.join(state_dir, REVOKED_FILE)
    temporary = path + '.tmp'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(revoked, f)
    os.replace(temporary, path)


def reconcile(api, members, state_dir='.'):
    """Disable the accounts of non-members and enable again the accounts
    the timer disabled whose users are members again. members is the set
    of lower-case mail addresses of the group members. Return a report."""
    revoked = _load_revoked(state_dir)
    report = {'disabled': [], 'enabled': []}
    for user in api.users():
        user_id, email = user['id'], (user.get('email') or '').strip().lower()
        member = bool(email) and email in members
        if not member and user.get('userEnabled'):
            # Disabling logs out every device of the account
            api.disable(user_id)
            revoked[user_id] = email
            _save_revoked(state_dir, revoked)
            report['disabled'].append(email)
        elif member and not user.get('userEnabled') and user_id in revoked:
            api.enable(user_id)
            del revoked[user_id]
            _save_revoked(state_dir, revoked)
            report['enabled'].append(email)
        elif user.get('userEnabled') and user_id in revoked:
            # Enabled again by an administrator
            del revoked[user_id]
            _save_revoked(state_dir, revoked)
    return report


def read_admin_token(env_path='vaultwarden.env'):
    with open(env_path) as f:
        for line in f:
            name, _, value = line.rstrip('\n').partition('=')
            if name == 'ADMIN_TOKEN' and value:
                return value
    raise RevokeError('ADMIN_TOKEN is missing in vaultwarden.env')
