*** Settings ***
Library    SSHLibrary
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

*** Test Cases ***
Install prototype modules
    ${idp_image} =    Evaluate    $IMAGE_URL.replace('/vaultwarden:', '/idp-vaultwarden-prototype:')
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
    Run task    module/${IDP}/set-client-access    {"domain":"${DOMAIN}","client_id":"${APP}","group_path":"/${GROUP}"}
    Policy is enforced

Activate application and verify private settings
    Run task    module/${APP}/configure-module    {"host":"${APP_HOST}","domain":"${DOMAIN}","idp_module":"${IDP}","required_group":"${GROUP}","lets_encrypt":false}
    Wait Until Keyword Succeeds    120s    3s    App is healthy
    ${mode} =    Execute Command    runagent -m ${APP} stat -c %a vaultwarden.env
    Should Be Equal    ${mode.strip()}    600
    ${rc} =    Execute Command    runagent -m ${APP} grep -Fx 'SSO_ONLY=true' vaultwarden.env    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    Policy is enforced

Application cannot change its access policy
    ${rc} =    Execute Command    runagent -m ${APP} api-cli run module/${IDP}/set-client-access --data '{"domain":"${DOMAIN}","client_id":"${APP}","group_path":"/other"}'    return_rc=True    return_stdout=False
    Should Not Be Equal As Integers    ${rc}    0
    Policy is enforced

Backup snapshot and service restart
    ${rc} =    Execute Command    runagent -m ${APP} module-dump-state    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${rc} =    Execute Command    runagent -m ${APP} tar tf vaultwarden-data.tar    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    Wait Until Keyword Succeeds    120s    3s    App is healthy
    ${rc} =    Execute Command    runagent -m ${APP} module-cleanup-state    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Remove application and IdP
    ${rc} =    Execute Command    remove-module --no-preserve ${APP}    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${rc} =    Execute Command    remove-module --no-preserve ${IDP}    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    Run task    cluster/remove-internal-domain    {"domain":"${DOMAIN}"}    decode_json=${FALSE}
