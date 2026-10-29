# 0006: Runtime, NS8 administrator sessions and stateless revocation

Status: implemented on the security work branch; not released or deployed.
Supersedes the token-export design of ADR 0005 and disable/enable bookkeeping
of ADR 0003. Source: user decisions P1–P21, 27 October 2026.

## Runtime and admin access (P2/P5/P17)

Use Vaultwarden 1.37.4 source commit
7c188967e7a467b19b2757bc3326f9cf3ccae327 and the matching upstream server image
(base digest is pinned in prototype/vaultwarden/Containerfile). Keep the
SSO-only API-key denial and managed-setting patches.
[Upstream release](https://github.com/dani-garcia/vaultwarden/releases/tag/1.37.4).

open-admin returns the URL, permitted frame ancestors and revoker status. It
never exports ADMIN_TOKEN. Managed password fields are masked in both value
and default in the rendered settings, including ADMIN_TOKEN and the SSO client
secret. Upgrade rotates the internal worker token to invalidate copies exposed
by previous releases; user credentials, SSO identity and vault keys are preserved.

Superseded on 29 October 2026 (security recheck R1/R5/R12, user decision for
one-time tickets): the first P5 bridge posted the NS8 login token of the
cluster manager to Vaultwarden, which kept it for 12 hours and replayed it
against the cluster API on every request. That token is a full owner bearer for
14 days and NS8 logout does not revoke it, so a compromised internet-facing
Vaultwarden would have exposed the cluster. Server-side replay also failed for
owners with a per-user IP allowlist. Now:

- NS8 authorizes open-admin for the user who runs it, in that user's browser
  request (including its IP allowlist). The action stores the SHA-256 of a
  random 60-second ticket and the NS8 user in admin-tickets/, mounted at
  /ns8-admin-tickets. Vaultwarden claims a ticket by renaming its file, so a
  ticket works once. No NS8 credential reaches Vaultwarden, and Vaultwarden
  makes no cluster API call.
- The login POST carries `<ticket>:<handle>`. The handle is a random value of
  the module page; Vaultwarden keeps its hash with the session. The browser gets
  a random HttpOnly SameSite=Strict NS8_ADMIN cookie.
- A session ends NS8_ADMIN_SESSION_SECONDS (120) after its last renewal. While
  the module page is open, it runs open-admin every 30 seconds and posts the new
  ticket with the handle to /admin/ns8/renew (no cookie, so a session in a
  separate tab is renewed too). Losing the right to run open-admin therefore
  ends admin access within 120 seconds instead of on the next request; this is
  the accepted trade-off of the decision. A failed renewal, restart or logout
  ends the session; an expired session cannot be revived.
- Whoever NS8 lets run open-admin may administer Vaultwarden: cluster owners
  and owners delegated on the module. Module agents get no ticket.
- Tickets and sessions are not in backups; tickets expire after 60 seconds and
  are purged by the next open-admin.

The Redis owner list considered first is not possible: module credentials read
only cluster/*, node/* and module/* keys, and role changes publish no event.

The worker uses a separate server-only X-NS8-Worker header carrying the existing
internal token. An old VW_ADMIN cookie alone is insufficient when managed mode
is active. The public static-token login cannot bypass the bridge. Login POSTs
from browsers require an explicitly permitted origin. Existing login rate
limits remain in place; no new P3 brute-force policy is introduced.

The admin page opens in a child iframe. Superseded on 29 October 2026 (user
decision): once embedded, the module page shows only the admin frame over the
whole application area, without heading, status or new-tab button. Warnings
(revocation problems, a session that cannot be renewed) are NS8 notifications
of the cluster manager, not part of the page. The new-tab button remains only where the
cluster manager may not embed the page. Consequence: if the browser withholds
the Strict cookie inside the frame (cluster manager and Vaultwarden on two
different sites, e.g. two co.uk domains), admin actions fail in the frame and
no fallback is offered.

Originally: the admin page opens in a child iframe, leaving a permanent new-tab
button available. No guessed last-two-domain-label rule is used. If Strict cookies or
browser framing restrictions prevent embedding, the explicit tab flow works
without taking over the cluster manager. General vault CSP policy is not
changed by P17A.

## Revocation (P6/P7/P8/P9/P10/P14)

Deploy the matching hardened IdP first. Registration enables access_required;
configuration and update require policy_required, policy_group_pinned and
policy_consumer_bound in addition to the enforced, enabled, matching group.
Vaultwarden registers expected_access_group from its own required_group setting.
An ordinary IdP policy edit cannot move that independent expectation: it closes
access until the original policy is restored, or explicit module reconfiguration
registers the newly intended group. A preflight may accept only this single
binding mismatch for a proposed matching group; the runtime worker always
requires the fully enforced binding. An older IdP cannot silently
activate the stateless worker. The timer checks the policy each run. A definite
mismatch logs out all accounts and reports failure.

Nonmembers are deauthenticated through the existing API. The worker NEVER
changes enabled. Group re-entry requires no local repair record. Administrative
locks are preserved. Existing revoked-users.json is retained for manual review;
no account in it is automatically enabled. Existing mail matching is retained:
the deployment fixes AD identities to their mail accounts. The original review
introduced mail mutation/recycling as a generic synthetic scenario without
showing that it was possible in this deployment (P11); it is not an accepted
operational defect or an authorization for a new identity subsystem.

CN and sAMAccountName are two attributes of ONE AD group, not evidence of two
configured groups. The previous IdP/worker paths searched different attributes.
The worker now uses CN consistently and rejects ambiguous matches. A separate
stable AD-GUID redesign was not selected by the user; the IdP policy pin uses
its persistent group ID.

Security recheck R3/R4 (29 October 2026): an IdP without the binding fields
of this release still ends all sessions, but the status reports the reason
idp_update_required and open-admin shows that the IdP needs an update; the update
hook stops with the same instruction. A user whose sessions cannot be ended no
longer stops the run: the other users are processed and the run reports the
failures (reason deauth_failed). Only an unreachable Vaultwarden stops a run.

The timer's policy check runs as an IdP task every two minutes. It sets
isNotificationHidden, so the cluster manager shows no "completed" notification
for it; failed checks are still notified by NS8 (29 October 2026).

revocation-status.json contains last attempt, last success, a safe failure code,
consecutive errors and a count of legacy locks. get-configuration returns it;
open-admin shows a warning on stale or repeatedly failing revocation. No tokens,
credentials or member address lists are put in status. A run is stale after six
minutes (timer interval two minutes); three consecutive errors also warn.

## Explicit deferrals and accepted behavior

P3 anti-brute-force planning and P13 full restore work remain open. P18A keeps
the consistent stop/export/restart backup: its service interruption is expected
and accepted, not a defect. P19 needs no fix. P20 is a real but low-impact error
message when configure precedes prepare-sso; it was explained, not authorized
for implementation in this decision round. P21 is the already agreed direct
membership restriction, not a demand for new UI explanations or nested groups.
