# 0003: Revocation timer with an internal admin token

Date: 2026-10-25. Status: implemented on branch `claude/reworked-hardening`,
not released. Base: 0.1.0-rc.1 (`f58aae6`), Vaultwarden 1.37.2.

User request (chat, 25.10.2026): implement the proposed revocation with an
internal admin token; asked whether offline vaults can be deactivated too.

## Problem

The IdP denies new logins and token refreshes of non-members at once, but
Vaultwarden takes the session expiry from the IdP access token
(`SSO_AUTH_ONLY_NOT_SESSION=false`): an existing session lasted up to 600 s
after a group removal. Vaultwarden has no OIDC back-channel logout.

## Decision

- `vaultwarden-revoke.timer` (every 2 minutes) runs `revoke-access`: it reads
  the mail addresses of the enabled direct members of the group from AD
  (NS8 ldapproxy, same filter semantics as the IdP check) and the accounts
  with the Vaultwarden admin API (`GET /admin/users`). Accounts of
  non-members are disabled (`POST /admin/users/<id>/disable`: resets the
  security stamp, deletes all devices, sends a logout); accounts disabled by
  the timer are enabled again when the user is a member again. Accounts are
  matched by e-mail address: the admin API exposes no SSO identifier.
- `revoked-users.json` records the accounts the timer disabled, so an account
  disabled by an administrator is never enabled by the timer. It is part of
  the backup.
- A missing group or an LDAP error changes nothing: an empty group is not
  taken for a failed lookup. New logins are denied by the IdP anyway.
- The admin API needs `ADMIN_TOKEN`: a random token (48 bytes) in
  `vaultwarden.env`, kept on re-registration and added by `update-module.d`
  to 0.1.0-rc.1 installations. It is stored as plain text: `vaultwarden hash`
  needs a terminal. The admin pages get a Traefik route of their own,
  `/admin` with `ip_allowlist` `127.0.0.1/32`, so Traefik denies them to
  every client; the timer calls the loopback port of the container. The admin
  session cookie is kept in `admin-session`, because Vaultwarden rate-limits
  admin logins (3 per 5 minutes by default).

## Offline vaults

Not possible on the server side. The clients keep an encrypted vault copy
that unlocks with the master password without the server, and delete it only
when they connect and are logged out. The Bitwarden policy that makes clients
log out after a maximum vault timeout (`MaximumVaultTimeout`, type 9) is not
supported by Vaultwarden 1.37.2 (`src/db/models/org_policy.rs`: "Not supported
(Not AGPLv3 Licensed)"). There is no remote wipe.
