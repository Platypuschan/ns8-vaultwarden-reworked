"""NS8 task calls; the app never receives IdP administration credentials."""
import json
import os
import agent
import agent.tasks
import vaultwarden_config as policy


def task(config, action, data):
    response = agent.tasks.run(agent_id='module/' + config['idp_module'], action=action, data=data)
    agent.assert_exp(response['exit_code'] == 0, f'IdP {action} failed')
    # NS8 task output is a JSON string, not a dictionary.
    output = response['output']
    return json.loads(output) if isinstance(output, str) else output


def prepare(config):
    if agent.get_bound_domain_list(agent.redis_connect()) != [config['domain']]:
        agent.bind_user_domains([config['domain']], check=True)
    registration = task(config, 'register-client', {
        'domain': config['domain'],
        'redirect_uris': ['https://' + config['host'] + '/identity/connect/oidc-signin'],
        'post_logout_redirect_uris': ['https://' + config['host'] + '/'],
    })
    env = policy.environment(config, registration)
    policy.private_write('vaultwarden.env', env)
    policy.private_write('settings.json', json.dumps(config))
    return registration
