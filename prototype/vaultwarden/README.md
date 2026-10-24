# Vaultwarden runtime patch

Upstream 1.37.2, source commit
`46d71107f5094460dd5ecbe1dbac6e6c71e5189a`. The included patch is licensed
under the upstream AGPL-3.0 terms (see LICENSE.txt); the surrounding NS8 module
and IdP integration use the repository's GPL-3.0 license.

The only behavioral change refuses `client_credentials` grants while both
`SSO_ENABLED` and `SSO_ONLY` are true. The official 1.37.2 image was tested with
a valid personal API key: it still issued a new-device token after AD group
removal. The patched runtime closes that path. Its explicit version is
`1.37.2-group-prototype`; sources, Cargo.lock and upstream runtime image are pinned.
