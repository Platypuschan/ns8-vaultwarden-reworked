# 0001: Enforce the application access group in the IdP

Date: 2026-10-24. Status: prototype implementation.
User requirement: only direct members of `services_vaultwarden` may log in to
Vaultwarden, including on a new device; local access to an already downloaded
vault is explicitly outside the revocation boundary. The AD `mail` attribute
contains unique addresses. No external federated IdP is required.

## Evidence and alternatives

- [Vaultwarden SSO settings](https://github.com/dani-garcia/vaultwarden/blob/1.37.2/.env.template)
  provide OIDC and SSO-only login, but no native group allowlist. An email-domain
  allowlist or a group claim alone does not implement the requirement.
- [NS8 IdP baseline](https://github.com/NethServer/ns8-idp/tree/433fa069c2eab4c073303769ac84c40b37a2676b)
  creates a read-only LDAP federation and a `LOAD_GROUPS_BY_MEMBER_ATTRIBUTE`
  group mapper. `register-client` preserves existing client attributes and flow
  overrides; it does not provide an access group setting.
- [Keycloak authentication flows](https://www.keycloak.org/docs/latest/server_admin/#_authentication-flows)
  distinguish alternative cookie/password executions from required executions.
  A check placed only inside the password form can be skipped by an SSO cookie.
- A conditional role/deny flow can fail open when the referenced role is
  deleted: [upstream condition implementation](https://github.com/keycloak/keycloak/blob/main/services/src/main/java/org/keycloak/authentication/authenticators/conditional/ConditionalRoleAuthenticator.java)
  returns false for a missing role. Avoid using that as the security boundary.

## Implementation

The prototype supplies a small Keycloak provider JAR, built against the exact
26.7.4 SPI used by the pinned ns8-idp Keycloak base. A private client browser
flow wraps a copy of the realm's normal browser flow as a REQUIRED subflow,
followed by a REQUIRED group gate. Cookie and password logins therefore both
reach the gate. The realm browser flow and unrelated clients are not replaced.

The group is stored by Keycloak group ID in administrator-owned client
attributes. The gate verifies live LDAP configuration, read-only mapper mode
and current direct membership. It rejects missing policy/group/user,
non-federated users, unsafe cache settings and LDAP errors. A required token
mapper repeats the check at token issuance, refresh and user-info processing;
this closes the interval between issuing an authorization code and redeeming
it after a group removal. It adds no claim that Vaultwarden could ignore.

The LDAP user provider uses `NO_CACHE`. This affects lookup performance for
all clients using that provider, not their access policy. Group objects are
synchronized when policy is applied; membership is read on requests. Nested
AD groups are not promised by this prototype. Use direct membership.

`set-client-access` is an administrative action, not part of `clientadm`.
The application can register its client and read its own policy using
`get-client-access`; it cannot remove its group restriction. Policy updates
disable the client before REST mutations and re-enable it only after a complete
validation. A partial failure leaves it disabled for administrator repair.

Vaultwarden activation requires a positive policy check for the expected group.
It uses SSO-only login, disables password signup, email-account matching and
invitations, and requires the IdP's verified email claim. Native provider refresh
tokens are used without requesting `offline_access` from Keycloak, so ordinary
realm/client session limits apply; Bitwarden's own `api offline_access` scope
is a separate protocol layer.

## Additional native Vaultwarden login path

Inspection and a positive runtime control on upstream 1.37.2 showed that
`SSO_ONLY=true` does not block `client_credentials` with a personal API key.
A valid existing key still issued a new-device token after group removal.
There is no configuration switch to disable this grant. The module therefore
uses a runtime built from upstream commit
`46d71107f5094460dd5ecbe1dbac6e6c71e5189a` plus the single guarded match arm in
`prototype/vaultwarden/deny-api-key-sso-only.patch`. In SSO-only mode it refuses
all `client_credentials` grants before they can register a device. This also
disables organization API-key login in the prototype. Normal SSO authorization
and refresh flows remain unchanged. No extra authentication reverse proxy is
introduced. The patch must be rebased and tested on every upstream upgrade.

## Boundaries

Group removal blocks new authorizations and token issuance/refresh. Existing
signed Vaultwarden access tokens may work until expiration. There is no remote
erasure of cached offline vaults. A real administrator with access to either
server can change policy; this does not defend against server administrators.

Manual changes to IdP policy topology are detected at activation, and runtime
gates reject unsafe LDAP settings. The prototype is not a general drift repair
controller. Changes to realm authentication/MFA after copying its browser flow
must be applied to the client flow as well. No external IdP/broker flow is tested.

A restored Vaultwarden instance remains disabled until it is registered again,
its policy is applied and it is explicitly configured. Its data is preserved.
Migration of an existing non-SSO account store and full cluster disaster recovery
are outside this initial prototype.

## NS8 event concurrency found by the QEMU test

On Core 3.23.2 / PostgreSQL, re-registering the existing client raced with
`keycloak-post-start` handling `module-domain-changed`. Both rewrote the same
LDAP component and PostgreSQL returned an optimistic-lock error. The prototype
overlay wraps reconciliation in the same `idprealm.realms_lock()` already used
by registrations and policy changes. The application also avoids rebinding an
unchanged user domain. This is a targeted correction to the pinned IdP baseline,
not a retry that conceals a failed configuration.
