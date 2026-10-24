# 0002: Group gate as a required action, compatible with upstream ns8-idp

Date: 2026-10-24. Status: prototype implementation. Supersedes the flow,
cache, token lifespan and administration parts of
[0001](0001-client-group-gate.md); its evidence and boundaries still apply.

Goal (user request, 24.10.2026): make the group policy suitable for the
original ns8-idp module without losing its features: federated IdPs (Entra
ID), the LDAP user cache, an optional token lifespan and a complete life
cycle. Sources: ns8-idp `433fa069`, Keycloak `26.7.4`, Vaultwarden `1.37.2`.

## Problems of the first prototype

- A private copy of the realm browser flow was bound to each restricted
  client. Later changes of the realm flow did not reach the copy: the
  `federated` login mode (`idpfed.apply_login_mode`), the password denial of
  federated accounts (`idpfed.ensure_password_denial`) and MFA changes.
- Logins through a federated IdP do not continue the browser flow
  (`IdentityBrokerService.finishBrokerAuthentication`): only the token gate
  checked them.
- The gate required a read-only LDAP federation, so it denied every user of
  a realm with a federated IdP, which upstream makes writable. The upstream
  group mapper stays read-only in that case (`idprealm.group_mapper_config`,
  `idpfed.ensure_writable_mappers`), and only the mapper decides where
  memberships come from.
- `NO_CACHE` was set on the shared LDAP federation. Keycloak does not
  validate cached users again (`UserStorageManager.importValidation`), and a
  cached user returns its cached group IDs, so some fix is needed, but not
  for every client of the realm.
- The policy set a 600 s access token lifespan, which is a Vaultwarden
  requirement (its session follows the IdP token, `sso.rs`; the Bitwarden
  front end refreshes 5 minutes before expiry), not part of access control.
- No removal; flows named after the client ID were left behind when a module
  was removed, and a new module with the same ID failed to set its policy.

A wrapper flow referencing the realm browser flow, instead of a copy, was
considered and rejected: Keycloak deletes referenced flows recursively when an
execution or flow is removed (`KeycloakModelUtils.deepDeleteAuthenticationExecutor`),
so re-pointing or removing the wrapper would delete the realm browser flow.

## Decision

- The `ns8-client-access` **required action**, enabled in the realm, checks
  the client of the authentication session. Keycloak evaluates the triggers of
  enabled required actions whenever an authentication completes
  (`AuthenticationManager.nextRequiredAction`), including SSO cookie and
  federated IdP logins. If the user is not allowed, the action is added to the
  authentication session only and shows an error page without a form. Realm
  flows and client flow bindings are not changed.
- The **token gate** protocol mapper stays on each restricted client: code
  redemption, refresh and user info.
- Both checks succeed for clients without the `ns8.access_policy=group`
  attribute. With it, a missing group, an LDAP error or a user that is not
  federated by an LDAP provider with the read-only group mapper is denied.
- **Cache**: the check evicts only the authenticating user from the user cache
  (`UserCache.evict`) and loads it again through the federation, then reads
  its LDAP memberships. A `StorageUnavailableUserModelDelegate` (LDAP down) is
  denied. The federation keeps its cache policy.
- **Administration**: `alter-realm-client` gets `access_group` (group name, or
  null to remove), under the realms lock. `get-client-access` (clientadm, own
  client only) reports `enforced` and the missing parts in `issues`;
  `list-realms` shows `access_group`.
- **Token lifespan**: optional `access_token_lifespan` of `register-client`
  (60-86400 s; missing keeps the current value, null restores the realm
  default). The Vaultwarden module requests 600 s.
- **Reconciliation** (`keycloak-post-start`, under the realms lock, which also
  fixes the concurrent LDAP component updates found in QEMU): enables the
  required action and restores token gates of restricted clients, which only
  makes them stricter; migrates first-prototype policies and removes their
  private flows (each references only its own copy, so the recursive deletion
  is limited to them).
- Java package `org.nethserver.keycloak.access`, like the upstream providers.

## Upstream changes

Only `idprealm.ensure_client`, `register-client`, `alter-realm-client`,
`list-realms` and `keycloak-post-start` change; `idpaccess.py`,
`get-client-access` and the provider are new. `idpfed.py` is unchanged. In
upstream the provider would join `keycloak-providers/ns8-authenticators`.

## Boundaries

As in 0001: existing signed Vaultwarden tokens stay valid until they expire
(600 s); no remote erasure of offline vaults; no defense against server
administrators. Nested AD groups are not supported. A renamed or removed group
denies everyone until the policy is set again. Admin changes made with the
Keycloak console between two reconciliations are not repaired immediately;
`get-client-access` reports them.
