"""NS8 task calls; the app never receives IdP administration credentials."""
import json
import os
import socket
import agent
import agent.tasks
import vaultwarden_config as policy


def task(config, action, data, quiet=False):
    # The cluster manager notifies every task without isNotificationHidden;
    # it still shows failed ones
    extra = {'isNotificationHidden': True} if quiet else {}
    response = agent.tasks.run(agent_id='module/' + config['idp_module'], action=action, data=data, extra=extra)
    agent.assert_exp(response['exit_code'] == 0, f'IdP {action} failed')
    # NS8 task output is a JSON string, not a dictionary.
    output = response['output']
    return json.loads(output) if isinstance(output, str) else output


ADMIN_ROUTE_SUFFIX = '-admin'


def configure_admin_route(traefik, config):
    """Expose the authenticated admin UI; NS8 owners log in via open-admin."""
    response = agent.tasks.run(agent_id=traefik, action='set-route', data={
        'instance': os.environ['MODULE_ID'] + ADMIN_ROUTE_SUFFIX,
        'url': 'http://127.0.0.1:' + os.environ['TCP_PORT'],
        'host': config['host'], 'path': '/admin', 'ip_allowlist': [],
        'http2https': True, 'lets_encrypt': config['lets_encrypt']})
    agent.assert_exp(response['exit_code'] == 0, 'Traefik admin route configuration failed')


def cluster_hostnames():
    """Node FQDNs that serve the cluster manager. set-fqdn keeps the VPN
    endpoints in sync with them."""
    names = [socket.getfqdn()]
    rdb = agent.redis_connect()
    for key in rdb.scan_iter('node/*/vpn'):
        names.append((rdb.hget(key, 'endpoint') or '').rsplit(':', 1)[0])
    return names


def prepare(config):
    if agent.get_bound_domain_list(agent.redis_connect()) != [config['domain']]:
        agent.bind_user_domains([config['domain']], check=True)
    registration = task(config, 'register-client', {
        'domain': config['domain'],
        'redirect_uris': ['https://' + config['host'] + '/identity/connect/oidc-signin'],
        'post_logout_redirect_uris': ['https://' + config['host'] + '/'],
        # Vaultwarden takes the session expiry from the IdP access token;
        # Bitwarden clients refresh 5 minutes before expiry, so a shorter
        # lifespan than 10 minutes makes them refresh on every request
        'access_token_lifespan': 600,
        'access_required': True,
        'expected_access_group': config['required_group'],
    })
    env = policy.environment(config, registration, policy.admin_token(),
        policy.frame_ancestors(cluster_hostnames()))
    policy.private_write('vaultwarden.env', env)
    policy.private_write('settings.json', json.dumps(config))
    return registration
