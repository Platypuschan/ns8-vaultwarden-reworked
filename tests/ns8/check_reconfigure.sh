#!/bin/bash
# Reproduce the PostgreSQL component-write race with real module processes.
set -Eeuo pipefail
idp="${1:?IdP module required}"
app="${2:?app module required}"
host="${3:?host required}"
domain="${4:?domain required}"
runagent -m "${idp}" keycloak-post-start &
reconcile_pid=$!
status=0
api-cli run "module/${app}/configure-module" --data - <<JSON || status=$?
{"host":"${host}","domain":"${domain}","idp_module":"${idp}","required_group":"services_vaultwarden","lets_encrypt":false}
JSON
wait "${reconcile_pid}" || status=$?
exit "${status}"
