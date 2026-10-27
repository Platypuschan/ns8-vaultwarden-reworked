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
by previous releases; user credentials, SSO identity and vault keys are preserved. The UI submits the current NS8 login token in a
POST body to the runtime. The runtime verifies it through the NS8 leader API
and confirms that the authenticated identity is a current cluster owner.
It stores the NS8 token only in process memory and gives the browser a random
HttpOnly SameSite=Strict NS8_ADMIN session cookie. The session has no independent
authority: EVERY protected request repeats the current NS8 authorization check.
Role removal, token expiry, missing owner membership, API failure or restart
therefore denies the request. A failed session cannot be revived by replaying
its cookie after a role regrant; logout deletes server-side state.

The existing supported NS8 API has no role-introspection endpoint. The bridge
therefore submits the read-only-in-effect list-users task and reads its result
on every request. Unlike a GET or a JWT role claim, task submission performs
current leader-side authorization; the task result identifies current owners.
This deliberately adds task/API traffic and a small wait to administrative
requests. No result is cached across requests. Calls use the local host API or
the cluster VPN endpoint, recomputed from leader metadata on every container
start, with redirects disabled. No core signing key or additional privilege is
copied to the module. A future dedicated core endpoint could replace this
transport without changing revocation semantics.

The worker uses a separate server-only X-NS8-Worker header carrying the existing
internal token. An old VW_ADMIN cookie alone is insufficient when managed mode
is active. The public static-token login cannot bypass the bridge. Login POSTs
from browsers require an explicitly permitted origin. Existing login rate
limits remain in place; no new P3 brute-force policy is introduced.

The admin page opens in a child iframe, leaving a permanent new-tab button
available. No guessed last-two-domain-label rule is used. If Strict cookies or
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
