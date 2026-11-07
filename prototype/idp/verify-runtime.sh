#!/bin/bash
# Fail closed before augmentation when a dependency bot changes only the POM/base.
set -euo pipefail
expected=$(cat /opt/keycloak/conf/ns8-keycloak-version)
actual=$(/opt/keycloak/bin/kc.sh --version)
[[ ${actual%%$'\n'*} == "Keycloak ${expected}" ]] || {
    printf 'Keycloak runtime/SPI mismatch: expected %s, got %s\n' "$expected" "$actual" >&2
    exit 1
}
for spi in core server-spi server-spi-private model-storage services; do
    test -f "/opt/keycloak/lib/lib/main/org.keycloak.keycloak-${spi}-${expected}.jar"
done
for provider in ns8-authenticators ns8-mappers ns8-client-access; do
    test -s "/opt/keycloak/providers/${provider}.jar" || {
        printf 'NS8 provider missing or empty: %s.jar\n' "$provider" >&2
        exit 1
    }
done
test -x /opt/keycloak/bin/ns8-healthcheck
