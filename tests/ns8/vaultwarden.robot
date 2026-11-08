*** Settings ***
Library    SSHLibrary
Library    OperatingSystem
Resource    api.resource

*** Variables ***
${IMAGE_URL}    ghcr.io/platypuschan/vaultwarden:codex-vaultwarden-sso
${IDP_HOST}    sso.fqdn.test
${APP_HOST}    vaultwarden.fqdn.test
${DOMAIN}    ad.fqdn.test
${GROUP}    services_vaultwarden
${APP}    ${EMPTY}
${IDP}    ${EMPTY}
${SAMBA}    ${EMPTY}
${RESTORED}    ${EMPTY}

*** Keywords ***
App is healthy
    ${rc} =    Execute Command    curl -kfsS --resolve ${APP_HOST}:443:127.0.0.1 https://${APP_HOST}/alive    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Roll back to
    [Arguments]    ${image}
    ${key_before} =    Execute Command    runagent -m ${APP} podman exec vaultwarden-app sha256sum /data/rsa_key.pem
    ${db_before} =    Execute Command    runagent -m ${APP} podman exec vaultwarden-app sh -c 'cat /data/rollback-marker'
    Run task    cluster/update-module    {"module_url":"${image}","instances":["${APP}"]}    decode_json=${FALSE}
    Wait Until Keyword Succeeds    180s    3s    App is healthy
    ${key_after} =    Execute Command    runagent -m ${APP} podman exec vaultwarden-app sha256sum /data/rsa_key.pem
    ${db_after} =    Execute Command    runagent -m ${APP} podman exec vaultwarden-app sh -c 'cat /data/rollback-marker'
    Should Be Equal    ${key_before.strip()}    ${key_after.strip()}
    Should Be Equal    ${db_before.strip()}    ${db_after.strip()}
    Policy is enforced
    ${rc} =    Execute Command    runagent -m ${APP} systemctl --user is-enabled --quiet vaultwarden-revoke.timer    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Host is healthy
    [Arguments]    ${host}
    ${rc} =    Execute Command    curl -kfsS --resolve ${host}:443:127.0.0.1 https://${host}/alive    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Policy is enforced
    ${policy} =    Run task    module/${IDP}/get-client-access    {"domain":"${DOMAIN}","client_id":"${APP}"}
    Should Be True    ${policy['enforced']}
    Should Be True    ${policy['enabled']}
    Should Be Equal    ${policy['group_path']}    /${GROUP}
    Should Be Empty    ${policy['issues']}

Discovery is reachable from app
    # The QEMU fixture uses a self-signed certificate. -k is confined to
    # this test; production configure-module verifies trusted HTTPS.
    ${out}    ${rc} =    Execute Command    runagent -m ${APP} podman exec vaultwarden-app curl -kfsS --connect-timeout 5 --max-time 15 https://${IDP_HOST}/realms/${DOMAIN}/.well-known/openid-configuration    return_rc=True
    Should Be Equal As Integers    ${rc}    0    ${out}
    ${metadata} =    Evaluate    json.loads($out)    modules=json
    Should Be Equal    ${metadata['issuer']}    https://${IDP_HOST}/realms/${DOMAIN}

IdP client identity
    ${out}    ${rc} =    Execute Command    runagent -m ${IDP} python3 -c 'import json,hashlib,kcadmin; k=kcadmin.agent_client(); c=k.find_client("${DOMAIN}","${APP}"); secret=k.get("/${DOMAIN}/clients/"+c["id"]+"/client-secret")["value"]; print(json.dumps({"realm":k.get("/${DOMAIN}")["id"],"client":c["id"],"group":c["attributes"]["ns8.access_group_id"],"secret_sha256":hashlib.sha256(secret.encode()).hexdigest()},sort_keys=True))'    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    RETURN    ${out}

*** Test Cases ***
Install released IdP rc.3 and Vaultwarden rc.4 for upgrade
    ${out}    ${rc} =    Execute Command    add-module ghcr.io/platypuschan/idp-reworked:0.1.0-rc.3 1    return_rc=True
    Should Be Equal As Integers    ${rc}    0    ${out}
    ${data} =    Evaluate    ast.literal_eval($out)    modules=ast
    Set Suite Variable    ${IDP}    ${data['module_id']}
    Run task    module/${IDP}/configure-module    {"host":"${IDP_HOST}","lets_encrypt":false}    decode_json=${FALSE}
    ${out}    ${rc} =    Execute Command    add-module ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.4 1    return_rc=True
    Should Be Equal As Integers    ${rc}    0    ${out}
    ${data} =    Evaluate    ast.literal_eval($out)    modules=ast
    Set Suite Variable    ${APP}    ${data['module_id']}

Create internal Samba domain
    ${out} =    Run task    cluster/add-internal-provider    {"image":"samba","node":1}
    Set Suite Variable    ${SAMBA}    ${out['module_id']}
    ${defaults} =    Run task    module/${SAMBA}/get-defaults    {"provision":"new-domain"}
    ${ip} =    Set Variable    ${defaults['ipaddress_list'][0]['ipaddress']}
    Run task    module/${SAMBA}/configure-module    {"provision":"new-domain","realm":"${DOMAIN}","nbdomain":"VWTEST","hostname":"dc1","ipaddress":"${ip}","adminuser":"administrator","adminpass":"Nethesis,1234"}    decode_json=${FALSE}
    Run task    module/${SAMBA}/add-user    {"user":"allowed","display_name":"Allowed User","password":"Nethesis,1234","mail":"allowed@fqdn.test"}    decode_json=${FALSE}
    Run task    module/${SAMBA}/add-user    {"user":"denied","display_name":"Denied User","password":"Nethesis,1234","mail":"denied@fqdn.test"}    decode_json=${FALSE}
    Run task    module/${SAMBA}/add-group    {"group":"${GROUP}","description":"Vaultwarden access","users":["allowed"]}    decode_json=${FALSE}

Prepare OIDC registration without exposing application
    ${data} =    Run task    module/${APP}/prepare-sso    {"host":"${APP_HOST}","domain":"${DOMAIN}","idp_module":"${IDP}","required_group":"${GROUP}","lets_encrypt":false}
    Should Be Equal    ${data['client_id']}    ${APP}
    ${out}    ${rc} =    Execute Command    api-cli run module/${APP}/configure-module --data '{"host":"${APP_HOST}","domain":"${DOMAIN}","idp_module":"${IDP}","required_group":"${GROUP}","lets_encrypt":false}'    return_rc=True
    Should Not Be Equal As Integers    ${rc}    0
    ${rc} =    Execute Command    runagent -m ${APP} systemctl --user is-active --quiet vaultwarden.service    return_rc=True    return_stdout=False
    Should Not Be Equal As Integers    ${rc}    0

Apply administrator group policy
    # Import group objects once; login membership is queried live through LDAP.
    ${rc} =    Execute Command    runagent -m ${IDP} python3 -c 'import kcadmin; k=kcadmin.agent_client(); r="${DOMAIN}"; s=k.get("/"+r+"/components",params={"type":"org.keycloak.storage.UserStorageProvider"})[0]; [k.post("/"+r+"/user-storage/"+s["id"]+"/mappers/"+m["id"]+"/sync?direction=fedToKeycloak") for m in k.get("/"+r+"/components",params={"parent":s["id"]}) if m["providerId"]=="group-ldap-mapper"]'    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    Run task    module/${IDP}/alter-realm-client    {"domain":"${DOMAIN}","client_id":"${APP}","access_group":"${GROUP}"}    decode_json=${FALSE}
    Policy is enforced
    ${realms} =    Run task    module/${IDP}/list-realms    {}
    ${clients} =    Evaluate    [c for r in $realms['realms'] if r['name'] == $DOMAIN for c in r['clients'] if c['client_id'] == $APP]
    Should Be Equal    ${clients[0]['access_group']}    ${GROUP}

Activate application and verify private settings
    Run task    module/${APP}/configure-module    {"host":"${APP_HOST}","domain":"${DOMAIN}","idp_module":"${IDP}","required_group":"${GROUP}","lets_encrypt":false}
    Wait Until Keyword Succeeds    120s    3s    App is healthy
    ${mode} =    Execute Command    runagent -m ${APP} stat -c %a vaultwarden.env
    Should Be Equal    ${mode.strip()}    600
    ${rc} =    Execute Command    runagent -m ${APP} grep -Fx 'SSO_ONLY=true' vaultwarden.env    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    Policy is enforced

Upgrade configured IdP rc.3 while preserving realm and client identity
    ${before} =    IdP client identity
    ${idp_image} =    OperatingSystem.Get File    ${CURDIR}/../../IDP_IMAGE
    ${idp_image} =    Evaluate    $idp_image.strip()
    Run task    cluster/update-module    {"module_url":"${idp_image}","instances":["${IDP}"]}    decode_json=${FALSE}
    Wait Until Keyword Succeeds    180s    3s    Discovery is reachable from app
    Wait Until Keyword Succeeds    120s    3s    Policy is enforced
    ${after} =    IdP client identity
    Should Be Equal    ${before.strip()}    ${after.strip()}
    ${expected} =    Execute Command    runagent -m ${IDP} printenv IDP_REWORKED_KEYCLOAK_IMAGE
    ${running} =    Execute Command    runagent -m ${IDP} podman inspect --format '{{.ImageName}}' keycloak
    Should Be Equal    ${running.strip()}    ${expected.strip()}

Public Keycloak admin paths are blocked while the home redirect remains public
    ${ip} =    Execute Command    hostname -I | awk '{print $1}'
    ${code} =    Execute Command    curl -sk -o /dev/null -w '\%{http_code}' --resolve ${IDP_HOST}:443:${ip.strip()} https://${IDP_HOST}/admin/realms
    Should Be Equal    ${code}    403
    ${code} =    Execute Command    curl -sk -o /dev/null -w '\%{http_code}' --resolve ${IDP_HOST}:443:${ip.strip()} https://${IDP_HOST}/realms/master/ns8-home
    Should Be Equal    ${code}    302

Upgrade configured installation to released rc.7 before regression check
    Run task    cluster/update-module    {"module_url":"ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.7","instances":["${APP}"]}    decode_json=${FALSE}
    Wait Until Keyword Succeeds    120s    3s    App is healthy
    ${rc} =    Execute Command    runagent -m ${APP} grep -Fx 'SSO_AUTH_ONLY_NOT_SESSION=false' vaultwarden.env    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Upgrade configured rc.7 to persistent device sessions
    ${worker_before} =    Execute Command    runagent -m ${APP} sh -c "grep '^ADMIN_TOKEN=' vaultwarden.env | sha256sum"
    ${env_before} =    Execute Command    runagent -m ${APP} sh -c "grep -v -E '^(NS8_MANAGED_CONFIG|ADMIN_RATELIMIT_MAX_BURST|ALLOWED_IFRAME_ANCESTORS|ADMIN_TOKEN|NS8_ADMIN_SESSION_SECONDS|SSO_AUTH_ONLY_NOT_SESSION)=' vaultwarden.env | sha256sum"
    ${key_before} =    Execute Command    runagent -m ${APP} podman exec vaultwarden-app sha256sum /data/rsa_key.pem
    Run task    cluster/update-module    {"module_url":"${IMAGE_URL}","instances":["${APP}"]}    decode_json=${FALSE}
    Wait Until Keyword Succeeds    120s    3s    App is healthy
    ${env_after} =    Execute Command    runagent -m ${APP} sh -c "grep -v -E '^(NS8_MANAGED_CONFIG|ADMIN_RATELIMIT_MAX_BURST|ALLOWED_IFRAME_ANCESTORS|ADMIN_TOKEN|NS8_ADMIN_SESSION_SECONDS|SSO_AUTH_ONLY_NOT_SESSION)=' vaultwarden.env | sha256sum"
    ${key_after} =    Execute Command    runagent -m ${APP} podman exec vaultwarden-app sha256sum /data/rsa_key.pem
    ${worker_after} =    Execute Command    runagent -m ${APP} sh -c "grep '^ADMIN_TOKEN=' vaultwarden.env | sha256sum"
    Should Not Be Equal    ${worker_before.strip()}    ${worker_after.strip()}
    ${required} =    Run task    module/${IDP}/get-client-access    {"domain":"${DOMAIN}","client_id":"${APP}"}
    Should Be True    ${required['policy_required']}
    Should Be True    ${required['policy_group_pinned']}
    Should Be True    ${required['policy_consumer_bound']}
    Should Be Equal    ${env_before.strip()}    ${env_after.strip()}
    Should Be Equal    ${key_before.strip()}    ${key_after.strip()}
    ${rc} =    Execute Command    runagent -m ${APP} grep -Fx 'SSO_AUTH_ONLY_NOT_SESSION=true' vaultwarden.env    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${value} =    Execute Command    runagent -m ${APP} podman exec vaultwarden-app printenv SSO_AUTH_ONLY_NOT_SESSION
    Should Be Equal    ${value.strip()}    true
    # The update lets the cluster manager on the node embed the admin page.
    ${rc} =    Execute Command    runagent -m ${APP} grep -Eq '^ALLOWED_IFRAME_ANCESTORS=https://[^ ]+' vaultwarden.env    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    Policy is enforced
    ${rc} =    Execute Command    runagent -m ${APP} test -f vaultwarden-network.env    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Rollback to the previous releases and forward again
    # Downgrades are not supported by NS8 itself; the data and the access policy must survive them anyway
    Execute Command    runagent -m ${APP} podman exec vaultwarden-app sh -c 'echo rollback-marker-4712 > /data/rollback-marker'
    Roll back to    ghcr.io/platypuschan/vaultwarden-reworked:0.1.0
    Roll back to    ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.7
    Roll back to    ${IMAGE_URL}
    ${value} =    Execute Command    runagent -m ${APP} podman exec vaultwarden-app printenv SSO_AUTH_ONLY_NOT_SESSION
    Should Be Equal    ${value.strip()}    true

Fresh installation of corrected package
    ${out}    ${rc} =    Execute Command    add-module ${IMAGE_URL} 1    return_rc=True
    Should Be Equal As Integers    ${rc}    0    ${out}
    ${data} =    Evaluate    ast.literal_eval($out)    modules=ast
    ${fresh} =    Set Variable    ${data['module_id']}
    ${host} =    Set Variable    vaultwarden-fresh.fqdn.test
    Run task    module/${fresh}/prepare-sso    {"host":"${host}","domain":"${DOMAIN}","idp_module":"${IDP}","required_group":"${GROUP}","lets_encrypt":false}
    Run task    module/${IDP}/alter-realm-client    {"domain":"${DOMAIN}","client_id":"${fresh}","access_group":"${GROUP}"}    decode_json=${FALSE}
    Run task    module/${fresh}/configure-module    {"host":"${host}","domain":"${DOMAIN}","idp_module":"${IDP}","required_group":"${GROUP}","lets_encrypt":false}
    ${rc} =    Execute Command    runagent -m ${fresh} systemctl --user is-active --quiet vaultwarden.service    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${value} =    Execute Command    runagent -m ${fresh} podman exec vaultwarden-app printenv SSO_AUTH_ONLY_NOT_SESSION
    Should Be Equal    ${value.strip()}    true
    ${rc} =    Execute Command    runagent -m ${fresh} test -f vaultwarden-network.env    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${rc} =    Execute Command    remove-module --no-preserve ${fresh}    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Local IdP discovery survives container recreation
    ${backend} =    Execute Command    runagent -m ${APP} podman info --format '{{.Host.RootlessNetworkCmd}}'
    Skip If    '${backend.strip()}' != 'pasta'    This regression targets pasta; slirp4netns retains its DNS path
    Discovery is reachable from app
    ${before} =    Execute Command    runagent -m ${APP} podman inspect vaultwarden-app --format '{{.Id}}'
    ${rc} =    Execute Command    runagent -m ${APP} systemctl --user restart vaultwarden.service    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${after} =    Execute Command    runagent -m ${APP} podman inspect vaultwarden-app --format '{{.Id}}'
    Should Not Be Equal    ${before.strip()}    ${after.strip()}
    Discovery is reachable from app

Pasta gateway regression with trusted test certificate
    ${backend} =    Execute Command    runagent -m ${APP} podman info --format '{{.Host.RootlessNetworkCmd}}'
    Skip If    '${backend.strip()}' != 'pasta'    Requires pasta
    ${fixture} =    Set Variable    /tmp/vw-network-${APP}
    Execute Command    mkdir -p ${fixture}/tests/network ${fixture}/imageroot/pypkg
    SSHLibrary.Put File    ${CURDIR}/../network/run.py    ${fixture}/tests/network/run.py
    SSHLibrary.Put File    ${CURDIR}/../../imageroot/pypkg/vaultwarden_network.py    ${fixture}/imageroot/pypkg/vaultwarden_network.py
    SSHLibrary.Put File    ${CURDIR}/../../imageroot/pypkg/vaultwarden_config.py    ${fixture}/imageroot/pypkg/vaultwarden_config.py
    ${out}    ${err}    ${rc} =    Execute Command    runagent -m ${APP} sh -c 'VW_RUNTIME_IMAGE="$VAULTWARDEN_REWORKED_SERVER_IMAGE" python3 ${fixture}/tests/network/run.py'    return_rc=True    return_stdout=True    return_stderr=True
    Should Be Equal As Integers    ${rc}    0    ${out}\n${err}

Revocation timer and authenticated admin pages
    ${rc} =    Execute Command    runagent -m ${APP} systemctl --user is-enabled --quiet vaultwarden-revoke.timer    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${rc} =    Execute Command    runagent -m ${APP} grep -q '^ADMIN_TOKEN=.' vaultwarden.env    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    # The server holds only an Argon2id hash; the clear text is in a private file for the worker
    ${rc} =    Execute Command    runagent -m ${APP} grep -q '^ADMIN_TOKEN=.argon2id.v=19.' vaultwarden.env    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${mode} =    Execute Command    timeout 60 runagent -m ${APP} stat -c %a admin-worker.token
    Should Be Equal    ${mode.strip()}    600
    ${leak} =    Execute Command    timeout 60 runagent -m ${APP} sh -c 'grep -c -F -f admin-worker.token vaultwarden.env || true'
    Should Be Equal    ${leak.strip()}    0
    # Anonymous admin navigation is denied; the NS8 UI uses its authenticated POST bridge.
    ${ip} =    Execute Command    hostname -I | awk '{print $1}'
    ${code} =    Execute Command    curl -sk -o /dev/null -w '\%{http_code}' --resolve ${APP_HOST}:443:${ip.strip()} https://${APP_HOST}/admin
    Should Be Equal    ${code}    403
    ${code} =    Execute Command    curl -sk -o /dev/null -w '\%{http_code}' --resolve ${APP_HOST}:443:${ip.strip()} https://${APP_HOST}/alive
    Should Be Equal    ${code}    200
    # The timer service binds to LDAP and logs in to the admin API
    ${out}    ${err}    ${rc} =    Execute Command    timeout 150 runagent -m ${APP} systemctl --user start vaultwarden-revoke.service    return_rc=True    return_stdout=True    return_stderr=True
    ${journal} =    Execute Command    timeout 60 runagent -m ${APP} journalctl --user -u vaultwarden-revoke.service -n 30 --no-pager 2>&1
    Should Be Equal As Integers    ${rc}    0    ${err}\n${journal}
    ${rc} =    Execute Command    runagent -m ${APP} test -s admin-session    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Every NS8 administrator can open the admin page
    SSHLibrary.Put File    ${CURDIR}/../admin/ns8_access.py    /tmp/vw-ns8-admin-access.py
    ${out}    ${err}    ${rc} =    Execute Command    python3 /tmp/vw-ns8-admin-access.py ${APP} ${APP_HOST}    return_rc=True    return_stdout=True    return_stderr=True
    Should Be Equal As Integers    ${rc}    0    ${out}\n${err}
    Should Contain    ${out}    NS8 reader: admin access denied
    Should Contain    ${out}    Admin ticket: single use, session renewed with a new ticket
    Should Contain    ${out}    NS8 owner revocation: no new ticket, admin session ended within its lifetime
    Should Contain    ${out}    Module self-administration: admin login denied

Native admin pages use the real runtime and the cluster smarthost
    ${text} =    Execute Command    api-cli run module/${APP}/query-panel-data --data '{"section":"users"}'
    Should Not Contain    ${text}    securityStamp
    Should Not Contain    ${text}    privateKey
    ${users} =    Evaluate    json.loads($text)    modules=json
    Should Be Equal    ${users['section']}    users
    ${text} =    Execute Command    api-cli run module/${APP}/query-panel-data --data '{"section":"organizations"}'
    ${orgs} =    Evaluate    json.loads($text)    modules=json
    Should Be Equal    ${orgs['section']}    organizations
    ${text} =    Execute Command    api-cli run module/${APP}/query-panel-data --data '{"section":"diagnostics"}'
    ${diag} =    Evaluate    json.loads($text)    modules=json
    Should Not Be Empty    ${diag['data']['current_release']}
    ${text} =    Execute Command    api-cli run module/${APP}/query-panel-data --data '{"section":"settings"}'
    Should Not Contain    ${text}    sso_client_secret
    Should Not Contain    ${text}    "admin_token"
    ${settings} =    Evaluate    json.loads($text)    modules=json
    ${groups} =    Evaluate    [g['group'] for g in $settings['data']]
    Should Be Equal    ${groups}    ${{['settings', 'advanced', 'duo', 'smtp', 'email_2fa']}}
    # Normal settings are saved; module managed ones are refused
    Run task    module/${APP}/set-panel-settings    {"values":{"org_creation_users":"admin@example.test"}}
    ${rc} =    Execute Command    api-cli run module/${APP}/set-panel-settings --data '{"values":{"sso_only":false}}'    return_rc=True    return_stdout=False
    Should Not Be Equal As Integers    ${rc}    0
    Run task    module/${APP}/reset-panel-settings    {}
    # Mail: off, then custom again
    Run task    module/${APP}/set-smtp-mode    {"mode":"disabled"}
    ${rc} =    Execute Command    runagent -m ${APP} grep -Fx '_ENABLE_SMTP=false' vaultwarden.env    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    Wait Until Keyword Succeeds    120s    3s    App is healthy
    Run task    module/${APP}/set-smtp-mode    {"mode":"custom"}
    ${rc} =    Execute Command    runagent -m ${APP} grep -q '^NS8_MANAGED_FIELDS=' vaultwarden.env    return_rc=True    return_stdout=False
    Should Not Be Equal As Integers    ${rc}    0
    Wait Until Keyword Succeeds    120s    3s    App is healthy
    # Without a cluster smarthost the mode is refused
    ${rc} =    Execute Command    api-cli run module/${APP}/set-smtp-mode --data '{"mode":"smarthost"}'    return_rc=True    return_stdout=False
    Should Not Be Equal As Integers    ${rc}    0

Concurrent IdP reconciliation and reconfiguration
    SSHLibrary.Put File    ${CURDIR}/check_reconfigure.sh    /tmp/vaultwarden-reconfigure-test.sh
    ${rc} =    Execute Command    bash /tmp/vaultwarden-reconfigure-test.sh ${IDP} ${APP} ${APP_HOST} ${DOMAIN}    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    Policy is enforced
    Wait Until Keyword Succeeds    120s    3s    App is healthy

Application cannot change its access policy
    ${rc} =    Execute Command    runagent -m ${APP} api-cli run module/${IDP}/alter-realm-client --data '{"domain":"${DOMAIN}","client_id":"${APP}","access_group":null}'    return_rc=True    return_stdout=False
    Should Not Be Equal As Integers    ${rc}    0
    Policy is enforced

Backup snapshot and service restart
    ${out}    ${err}    ${rc} =    Execute Command    runagent -m ${APP} module-dump-state    return_rc=True    return_stdout=True    return_stderr=True
    Should Be Equal As Integers    ${rc}    0    ${err}
    ${files}    ${rc} =    Execute Command    runagent -m ${APP} tar tf vaultwarden-data.tar    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    Should Contain    ${files}    db.sqlite3
    Wait Until Keyword Succeeds    120s    3s    App is healthy
    ${rc} =    Execute Command    runagent -m ${APP} module-cleanup-state    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Restore from a cluster backup into a new module identity
    # P13: data, keys and settings survive a restore under a different module ID
    ${host} =    Set Variable    vaultwarden-restored.fqdn.test
    Execute Command    runagent -m ${APP} podman exec vaultwarden-app sh -c 'echo restore-marker-4711 > /data/restore-marker'
    ${key_orig} =    Execute Command    runagent -m ${APP} podman exec vaultwarden-app sha256sum /data/rsa_key.pem
    ${mark_orig} =    Execute Command    runagent -m ${APP} podman exec vaultwarden-app sha256sum /data/restore-marker
    ${settings_orig} =    Execute Command    runagent -m ${APP} sha256sum settings.json
    ${uuid} =    Execute Command    runagent -m ${APP} printenv MODULE_UUID
    ${ip} =    Execute Command    ip -4 -o addr show wg0 | awk '{print $4}' | cut -d/ -f1
    ${repo} =    Run task    cluster/add-backup-repository    {"name":"vw-restore-test","provider":"cluster","url":"webdav:http://${ip.strip()}:4694","password":"","parameters":{}}
    ${backup} =    Run task    cluster/add-backup    {"repository":"${repo['id']}","schedule":"daily","retention":1,"instances":["${APP}"],"enabled":true,"name":"vw-restore-test"}
    ${out}    ${err}    ${rc} =    Execute Command    runagent -m node run-backup --backup ${backup}    return_rc=True    return_stdout=True    return_stderr=True
    Should Be Equal As Integers    ${rc}    0    ${out}\n${err}
    ${content} =    Run task    cluster/read-backup-repositories    {}
    Log    ${content}
    ${path} =    Evaluate    [c['path'] for c in $content if c['uuid'] == $uuid.strip() and c['repository_id'] == $repo['id']][0]
    ${before} =    Execute Command    runagent -l
    Run task    cluster/restore-module    {"repository":"${repo['id']}","path":"${path}","snapshot":"","node":1,"replace":false}    decode_json=${FALSE}
    ${after} =    Execute Command    runagent -l
    ${new} =    Evaluate    [m for m in $after.split() if m.startswith('vaultwarden') and m not in $before.split()][0]
    Should Not Be Equal    ${new}    ${APP}
    Set Suite Variable    ${RESTORED}    ${new}
    # Restored settings are kept, the service and the revocation timer stay off until SSO is prepared again
    ${settings_new} =    Execute Command    runagent -m ${new} sha256sum settings.json
    Should Be Equal    ${settings_orig.strip()}    ${settings_new.strip()}
    ${rc} =    Execute Command    runagent -m ${new} systemctl --user is-active --quiet vaultwarden.service    return_rc=True    return_stdout=False
    Should Not Be Equal As Integers    ${rc}    0
    ${rc} =    Execute Command    runagent -m ${new} systemctl --user is-enabled --quiet vaultwarden-revoke.timer    return_rc=True    return_stdout=False
    Should Not Be Equal As Integers    ${rc}    0
    # Vault data is in the restored volume before anything starts
    ${data} =    Execute Command    runagent -m ${new} sh -c 'podman run --rm --network=none -v vaultwarden-data:/data:ro --entrypoint sh "$VAULTWARDEN_REWORKED_SERVER_IMAGE" -c "test -s /data/db.sqlite3 && sha256sum /data/rsa_key.pem /data/restore-marker"'
    Should Contain    ${data}    ${key_orig.split()[0]}
    Should Contain    ${data}    ${mark_orig.split()[0]}
    # New identity: new OIDC client, access policy, own host
    Run task    module/${new}/prepare-sso    {"host":"${host}","domain":"${DOMAIN}","idp_module":"${IDP}","required_group":"${GROUP}","lets_encrypt":false}
    Run task    module/${IDP}/alter-realm-client    {"domain":"${DOMAIN}","client_id":"${new}","access_group":"${GROUP}"}    decode_json=${FALSE}
    Run task    module/${new}/configure-module    {"host":"${host}","domain":"${DOMAIN}","idp_module":"${IDP}","required_group":"${GROUP}","lets_encrypt":false}
    Wait Until Keyword Succeeds    120s    3s    Host is healthy    ${host}
    ${policy} =    Run task    module/${IDP}/get-client-access    {"domain":"${DOMAIN}","client_id":"${new}"}
    Should Be True    ${policy['enforced']}
    Should Be Empty    ${policy['issues']}
    ${key_new} =    Execute Command    runagent -m ${new} podman exec vaultwarden-app sha256sum /data/rsa_key.pem
    ${mark_new} =    Execute Command    runagent -m ${new} podman exec vaultwarden-app sha256sum /data/restore-marker
    Should Be Equal    ${key_orig.strip()}    ${key_new.strip()}
    Should Be Equal    ${mark_orig.strip()}    ${mark_new.strip()}
    ${rc} =    Execute Command    runagent -m ${new} systemctl --user is-enabled --quiet vaultwarden-revoke.timer    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${rc} =    Execute Command    remove-module --no-preserve ${new}    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    Run task    cluster/remove-backup    {"id":${backup}}    decode_json=${FALSE}
    Run task    cluster/remove-backup-repository    {"id":"${repo['id']}"}    decode_json=${FALSE}

Remove application and IdP
    ${rc} =    Execute Command    remove-module --no-preserve ${APP}    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${rc} =    Execute Command    remove-module --no-preserve ${IDP}    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    Run task    cluster/remove-internal-domain    {"domain":"${DOMAIN}"}    decode_json=${FALSE}
