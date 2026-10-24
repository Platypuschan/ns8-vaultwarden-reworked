# ns8-vaultwarden — SSO group-filter prototype

Vaultwarden 1.37.2 (with the SSO-only API-key bypass closed) for NS8 with local Samba-AD authentication through ns8-idp.
Only direct members of an administrator-selected AD group can authorize the
Vaultwarden client or obtain/refresh its OIDC tokens. Existing SSO cookies do
not bypass the group check. The initial target group is `services_vaultwarden`.

This is a CLI/API prototype, not a stable catalog release. The unmodified
upstream ns8-idp does not provide this group gate: the accompanying IdP
prototype image is a required dependency. No production instance is changed
by development or tests.

- [Installation and IdP configuration (German)](docs/INSTALL-IDP.md)
- [Architecture, sources and access boundaries](docs/decisions/0001-client-group-gate.md)
- [Test procedure and evidence](docs/TESTING.md)

Runtime data stays in the module's `vaultwarden-data` volume. Configuration
and client secrets are in its private state directory; credentials are not
returned by `get-configuration`. No Vaultwarden admin panel/password-login
bypass is provided by this prototype.

Validated prototype: `prototype-89a52bc0f978`; NS8 Core 3.23.2 on Debian 13 and
Rocky 9, 9 module tests each. Configuration tests and 10 real Samba/Keycloak/
Vaultwarden protocol tests also pass. See the test report for exact commits,
image digests and the distinction between protocol and physical Android tests.
