# 0008: Keep enrolled device sessions independent of IdP browser sessions

Date: 2026-10-31. User request: restore Android vault unlocking with master
password or biometrics without completing SSO on every use.

## Finding

The module explicitly set `SSO_AUTH_ONLY_NOT_SESSION=false`. Vaultwarden
therefore embeds the Keycloak refresh token and its expiry in the device
refresh token. An idle or expired Keycloak session requires browser SSO again,
even when the user only wants to unlock an enrolled app. The actual user
installation and Android timeout settings have not been inspected.

## Decision

Set the managed `SSO_AUTH_ONLY_NOT_SESSION=true`. SSO remains mandatory for
initial device enrollment and after logout; subsequent device refresh uses
Vaultwarden's normal device session. Local locking, master password and
biometric unlocking remain client operations. The Android timeout action must
be **Lock**, because **Log out** deliberately deletes the enrolled session.
No Keycloak realm session extension or offline_access scope is necessary.

`prepare` generates the setting on installation/reconfiguration. Existing
`update-module.d/77access-policy` calls the same function before `80restart`,
so upgrades replace the old managed value in the existing environment file.
A still-valid previous token can refresh into a normal device token; already
expired tokens or deleted device records require one final SSO enrollment.

## Access removal and availability

New enrollments still pass the IdP's live AD group gate. Existing sessions
are revoked by the existing two-minute AD reconciliation timer via deauth;
policy mismatch deauthenticates all users. This becomes the authority for
existing device revocation. The timer must be running and healthy.

The pre-existing LDAP/transport error behavior is retained: failed lookups
are reported, not treated as an empty group. With independent device sessions,
an unavailable IdP/LDAP or a failed timer no longer causes existing devices to
expire with the short IdP session. Thus no bounded group-revocation guarantee
is made during worker failure. Status warnings remain essential. Offline vault
copies remain outside server-side revocation as previously agreed.

## Sources and verification

Runtime source pinned by the Containerfile:
[Vaultwarden 1.37.4 auth.rs](https://github.com/dani-garcia/vaultwarden/blob/7c188967e7a467b19b2757bc3326f9cf3ccae327/src/auth.rs)
(`refresh_tokens`, `AuthTokens::new`) and
[sso.rs](https://github.com/dani-garcia/vaultwarden/blob/7c188967e7a467b19b2757bc3326f9cf3ccae327/src/sso.rs).

The protocol suite uses the generated production setting. Test 18 enrolls a
mobile device, destroys its Keycloak sessions, refreshes without browser SSO,
restarts Vaultwarden and refreshes again. Test 20 removes the real Samba AD
group membership and verifies the worker invalidates that device's refresh
token. Physical Android biometric UI and the user's installation require a
separate live check; protocol success does not claim that check.
