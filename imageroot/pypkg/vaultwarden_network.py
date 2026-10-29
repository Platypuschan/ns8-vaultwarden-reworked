"""Reach a co-located IdP without routing through pasta's own guest address."""
import json
import subprocess
import time
from urllib.parse import urlsplit

import vaultwarden_config as policy


def read_issuer(path='vaultwarden.env'):
    with open(path) as stream:
        values = dict(line.rstrip('\n').split('=', 1) for line in stream if '=' in line)
    return values['SSO_AUTHORITY']


def network_options(config, issuer, local_node, idp_node, backend):
    url = urlsplit(issuer)
    if (url.scheme != 'https' or not url.hostname or not policy.HOST.fullmatch(url.hostname)
            or url.username or url.password or url.query or url.fragment
            or url.path != '/realms/' + config['domain']):
        raise ValueError('Unexpected OIDC issuer for container networking')
    if not local_node or not idp_node:
        raise ValueError('Cannot determine the IdP node; check NS8 module metadata')
    if str(local_node) == str(idp_node) and backend == 'pasta':
        return ['--add-host=' + url.hostname + ':host-gateway']
    return []


def prepare_network(config, issuer, rdb, local_node):
    # cluster/module_node is readable by module agents. Re-evaluate on each
    # start: a backup/restore or a relocated IdP must not retain a stale alias.
    idp_node = rdb.hget('cluster/module_node', config['idp_module'])
    backend = subprocess.check_output(
        ['podman', 'info', '--format', '{{.Host.RootlessNetworkCmd}}'], text=True).strip()
    options = network_options(config, issuer, local_node, idp_node, backend)
    policy.private_write('vaultwarden-network.env',
        'VAULTWARDEN_NETWORK_ARGS=' + ' '.join(options) + '\n')


def check_discovery(issuer, timeout=60, container='vaultwarden-app'):
    """Verify HTTPS from the real app container, including the returned issuer.

    Retry while Traefik obtains the certificate. Never log response bodies or
    curl stderr, and never turn off certificate verification.
    """
    deadline = time.monotonic() + timeout
    while True:
        result = subprocess.run([
            'podman', 'exec', container, 'curl', '--fail', '--silent',
            '--show-error', '--connect-timeout', '3', '--max-time', '8',
            issuer.rstrip('/') + '/.well-known/openid-configuration',
        ], capture_output=True, text=True)
        if result.returncode == 0:
            try:
                metadata = json.loads(result.stdout)
                if metadata.get('issuer') == issuer:
                    return
            except (ValueError, AttributeError):
                pass
        if time.monotonic() >= deadline:
            raise ValueError('OIDC discovery failed from vaultwarden-app: check IdP DNS, '
                'HTTPS certificate and container-to-host connectivity; see INSTALL-IDP.md')
        time.sleep(2)
