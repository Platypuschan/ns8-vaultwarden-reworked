# 0005: Direct Vaultwarden administration for every NS8 administrator

Date: 2026-10-26. Status: implemented, preparing rc.4.

The user explicitly requires every NS8 administrator to reach Vaultwarden’s admin page from Cluster Manager without tunnels or manual token handling. Replace the placeholder UI with an automatic authenticated handoff using the existing NS8 task/event bridge.

The `open-admin` action is intentionally outside the reader prefixes `get-`, `read-`, `show-` and `list-`. NS8 grants cluster owners the module-owner role, which already permits it. No new user, role or password is introduced. The action returns the configured HTTPS admin URL and existing internal admin token. The UI immediately submits it in a hidden POST form to the top-level admin page; it is not placed in a URL or local storage. Vaultwarden then issues its normal secure HttpOnly admin cookie. The token is privileged task output and must not be logged or exposed via reader actions.

The separate `/admin` Traefik route no longer rejects public clients by IP. Unauthenticated visitors get the standard admin login page, not admin privileges. Protected admin APIs still require a valid session. The internal revocation timer retains its token and local API path.

Normal admin settings in config.json are supported. A narrow runtime patch activated by NS8_MANAGED_CONFIG keeps module-managed SSO values, domain, admin token, signup/invitation policy and trusted proxy settings read-only. The same fields are ignored when loading saved config and when saving through the admin API. Other settings persist normally. Remove the former blanket config.json startup rejection. This keeps UI administration usable while preserving the agreed SSO-only/group gate and the timer’s internal token.

Update migrates existing environment files and replaces the old admin IP allowlist. Restore retains normal settings; module-managed values are reestablished by the existing SSO preparation/configuration flow. Destruction still removes both application and admin routes.

Verification: browser handoff against real Vaultwarden; actual NS8 authorization and login for two owners plus reader/module rejection; normal settings save and restart; unchanged SSO policy after attempted overrides. Existing protocol and pasta regression suites remain required.
