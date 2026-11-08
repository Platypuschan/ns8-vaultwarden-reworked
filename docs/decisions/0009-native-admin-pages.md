# 0009: Native NS8 pages instead of the Vaultwarden admin page

Date: 2026-11-08. Status: implemented on branch `claude/native-admin-ui`, not released.

Request: the module page in the cluster manager shows Settings, Users, Organizations and Diagnostics in the NS8 layout (side menu, Carbon components) instead of the embedded Vaultwarden admin page. The original page stays reachable as **Advanced admin page**. The web vault link is not rebuilt. Invitations are not offered: accounts are created by the first SSO sign-in (`SSO_SIGNUPS_ALLOWED=true`, `INVITATIONS_ALLOWED=false`).

## Design

- The pages call NS8 actions (`query-panel-data`, `set-panel-settings`, `reset-panel-settings`, `manage-user`, `manage-organization`, `test-smtp`, `set-smtp-mode`). The actions use the Vaultwarden admin API on the loopback port with the internal worker credential (the one the revocation timer already uses). No Vaultwarden credential reaches the browser.
- The runtime patch adds read-only JSON views for the worker: `/admin/ns8/data/{settings,users,organizations,diagnostics}`. They return what the HTML admin pages render.
- None of the new actions starts with `get-`, `read-`, `show-` or `list-`: NS8 lets cluster readers run those, and these actions expose users, settings and the SMTP password. A unit test keeps it that way.
- Users are reduced to the displayed fields before they leave the module. The upstream user record also holds the encrypted account keys and the security stamp; they must not reach the browser or the task log.
- Settings: General, Advanced, Global Duo, SMTP and Email 2FA are offered. OpenID Connect is not shown, and Yubikey is not offered. Fields that Vaultwarden marks read-only (everything the module manages) are not shown at all. Vaultwarden replaces its whole `config.json` on every save, so the module sends the complete set of non-default values (also those of groups the page does not show) and drops cleared or default values.
- SMTP mode: `disabled`, `smarthost` (host, port, encryption, login and certificate check from the cluster smarthost, rest custom) or `custom`. The mode is stored in `smtp-mode.json` and rendered into `vaultwarden.env` (`_ENABLE_SMTP`, `SMTP_*`, `NS8_MANAGED_FIELDS`). `NS8_MANAGED_FIELDS` is a comma list of settings that the runtime treats as read-only and ignores in `config.json`. The `smarthost-changed` event refreshes the environment and restarts the service. Existing installations start in `custom`, so nothing changes for them.
- The Advanced admin page keeps the ticket flow of `open-admin` (ADR 0005), now inside the module page next to the menu.

## Not covered

Upstream "Backup database" and the support configuration download, the Yubikey group, invitations and the web vault link. The English field labels and help texts come from Vaultwarden and are not translated; menus, buttons and messages are in English and German.
