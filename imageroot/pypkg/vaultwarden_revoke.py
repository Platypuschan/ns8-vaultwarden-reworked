"""Log out nonmembers without changing administrative account locks.

AD accounts and mail accounts are linked by deployment policy. The worker
uses their mail address for the existing Vaultwarden account mapping.
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


class UnavailableError(RevokeError):
    """Vaultwarden cannot be reached: no further request can succeed."""


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
            search_filter=f'(&(objectCategory=group)(cn={escape_filter_chars(group)}))',
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
        request = urllib.request.Request(self.base_url + path, data=body, method=method, headers=dict(headers or {}, **{'X-NS8-Worker': self.token}))
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            with opener.open(request, timeout=30) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read()
        except (urllib.error.URLError, OSError) as error:
            raise UnavailableError(f'Vaultwarden is not reachable: {type(error).__name__}') from None

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

    def deauth(self, user_id):
        self.request('POST', f'/admin/users/{urllib.parse.quote(user_id, safe="")}/deauth')


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
    except (ValueError, OSError):
        return None


def reconcile(api, members, state_dir='.'):
    """End the sessions of nonmembers. Never disable or re-enable accounts.

    Legacy disabled accounts stay disabled for administrative review; the
    old journal is retained, but is no longer an authority to enable anyone.
    A user whose sessions cannot be ended does not stop the others: the
    caller reports the failures. Only an unreachable Vaultwarden stops.
    """
    legacy = _load_revoked(state_dir)
    report = {'deauthenticated': 0, 'failed': 0, 'legacy_disabled': len(legacy) if isinstance(legacy, dict) else None}
    for user in api.users():
        email = (user.get('email') or '').strip().lower()
        if not email or email not in members:
            try:
                api.deauth(user['id'])
            except UnavailableError:
                raise
            except RevokeError:
                report['failed'] += 1
                continue
            report['deauthenticated'] += 1
    return report


def read_admin_token(env_path='vaultwarden.env'):
    with open(env_path) as f:
        for line in f:
            name, _, value = line.rstrip('\n').partition('=')
            if name == 'ADMIN_TOKEN' and value:
                return value
    raise RevokeError('ADMIN_TOKEN is missing in vaultwarden.env')


STATUS_FILE = 'revocation-status.json'

def initialize_status(state_dir='.'):
    from datetime import datetime, timezone
    from pathlib import Path
    from vaultwarden_config import private_write
    path = Path(state_dir) / STATUS_FILE
    if not path.exists():
        private_write(path, json.dumps({'monitor_started': datetime.now(timezone.utc).isoformat(),
            'last_success': None, 'last_error': None, 'consecutive_errors': 0}))


def write_status(error=None, report=None, state_dir='.', reason=None):
    from datetime import datetime, timezone
    from vaultwarden_config import private_write
    from pathlib import Path
    path = Path(state_dir) / STATUS_FILE
    try:
        previous = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        previous = {}
    if not isinstance(previous, dict):
        previous = {}
    now = datetime.now(timezone.utc).isoformat()
    status = {
        'last_attempt': now,
        'last_success': previous.get('last_success') if error else now,
        'last_error': error,
        'consecutive_errors': previous.get('consecutive_errors', 0) + 1 if error else 0,
        'legacy_disabled': (report or {}).get('legacy_disabled', previous.get('legacy_disabled', 0)),
    }
    if reason:
        status['reason'] = reason
    private_write(path, json.dumps(status))
    return status


def status(state_dir='.'):
    from datetime import datetime, timezone
    from pathlib import Path
    try:
        result = json.loads((Path(state_dir) / STATUS_FILE).read_text())
    except FileNotFoundError:
        return {'state': 'pending', 'last_success': None, 'consecutive_errors': 0}
    except ValueError:
        return {'state': 'warning', 'last_success': None, 'consecutive_errors': 0}
    if not isinstance(result, dict):
        return {'state': 'warning', 'last_success': None, 'consecutive_errors': 0}
    success = result.get('last_success')
    baseline = success or result.get('monitor_started')
    try:
        stale = not baseline or (datetime.now(timezone.utc) - datetime.fromisoformat(baseline)).total_seconds() > 360
    except (ValueError, TypeError):
        stale = True
    result['state'] = 'warning' if stale or result.get('consecutive_errors', 0) >= 3 else ('ok' if success else 'pending')
    return result
