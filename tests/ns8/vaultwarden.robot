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

*** Keywords ***
App is healthy
    ${rc} =    Execute Command    curl -kfsS --resolve ${APP_HOST}:443:127.0.0.1 https://${APP_HOST}/alive    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Policy is enforced
    ${policy} =    Run task    module/${IDP}/get-client-access    {"domain":"${DOMAIN}","client_id":"${APP}"}
    Should Be True    ${policy['enforced']}
    Should Be True    ${policy['enabled']}
    Should Be Equal    ${policy['group_path']}    /${GROUP}
    Should Be Empty    ${policy['issues']}

*** Test Cases ***
Install reworked modules
    ${idp_image} =    OperatingSystem.Get File    ${CURDIR}/../../IDP_IMAGE
    ${idp_image} =    Evaluate    $idp_image.strip()
    ${out}    ${rc} =    Execute Command    add-module ${idp_image} 1    return_rc=True
    Should Be Equal As Integers    ${rc}    0    ${out}
    ${data} =    Evaluate    ast.literal_eval($out)    modules=ast
    Set Suite Variable    ${IDP}    ${data['module_id']}
    Run task    module/${IDP}/configure-module    {"host":"${IDP_HOST}","lets_encrypt":false}    decode_json=${FALSE}
    ${out}    ${rc} =    Execute Command    add-module ${IMAGE_URL} 1    return_rc=True
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

Revocation timer and private admin pages
    ${rc} =    Execute Command    runagent -m ${APP} systemctl --user is-enabled --quiet vaultwarden-revoke.timer    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${rc} =    Execute Command    runagent -m ${APP} grep -q '^ADMIN_TOKEN=.' vaultwarden.env    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    # Traefik allows the admin pages to the loopback address only: connect
    # from the node address
    ${ip} =    Execute Command    hostname -I | awk '{print $1}'
    ${code} =    Execute Command    curl -sk -o /dev/null -w '\%{http_code}' --resolve ${APP_HOST}:443:${ip.strip()} https://${APP_HOST}/admin
    Should Be Equal    ${code}    403
    ${code} =    Execute Command    curl -sk -o /dev/null -w '\%{http_code}' --resolve ${APP_HOST}:443:${ip.strip()} https://${APP_HOST}/alive
    Should Be Equal    ${code}    200
    # The timer service binds to LDAP and logs in to the admin API
    ${out}    ${err}    ${rc} =    Execute Command    runagent -m ${APP} systemctl --user start vaultwarden-revoke.service    return_rc=True    return_stdout=True    return_stderr=True
    Should Be Equal As Integers    ${rc}    0    ${err}
    ${rc} =    Execute Command    runagent -m ${APP} test -s admin-session    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

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

Remove application and IdP
    ${rc} =    Execute Command    remove-module --no-preserve ${APP}    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${rc} =    Execute Command    remove-module --no-preserve ${IDP}    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    Run task    cluster/remove-internal-domain    {"domain":"${DOMAIN}"}    decode_json=${FALSE}
