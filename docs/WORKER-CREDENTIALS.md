# Worker credential lifecycle

`worker-credential.json` is the authoritative private (0600) record: credential
schema, random worker token, and its Argon2id PHC hash. `vaultwarden.env` contains
only the derived `ADMIN_TOKEN` hash. `admin-worker.token` is a legacy import, not
a second authority; migration removes it after committing the new projection.
The backup allowlist retains the legacy name and includes the canonical record.

## Updates and recovery

All writers call `ensure_worker_credential()` under the agent's `configuration`
lock. It verifies the secret against the real Argon2id hash, not just its syntax.
A valid pair is imported unchanged. Subsequent updates do not generate a token
or hash and do not rewrite an already correct canonical record/projection.
Rotation requires an explicit request or a supported credential-schema change.
Unknown schema versions fail closed rather than downgrading newer records.

The record is written with a private temporary file, file fsync, atomic replace,
and parent-directory fsync **before** updating the environment projection. If
interrupted between these operations, startup refuses an incoherent pair; the
next locked ensure replays the projection without generating another token.
Other environment lines (including OIDC/SMTP configuration) are retained.

The module bundles Debian Bullseye's `libargon2.so.1` from a digest-pinned build
stage (including its license). Its stable C ABI avoids dependencies on a host
Python wheel/version or the presence of a host Argon2 package. Tests outside a
built module use the host's `libargon2-1`. Verification is local in-process;
neither token nor PHC is passed through argv or environment. Generation still
uses the existing isolated `vaultwarden hash` PTY, with the token sent through
the terminal only. Verification bounds PHC costs before invoking native code.

`77access-policy`, the independent `80restart` check, systemd's ExecStartPre,
and the worker's token reader all check coherence. Core can continue after a
failed hook: `80restart` therefore stops the app/timer/worker on a failed check
instead of restarting an unprotected app. Service and worker gates are read-only;
they do not repair state or implicitly rotate. The service gate must not acquire
the configuration lock: configure-module waits for systemd while holding it.

## Backup/restore and legacy state

Restore remains disabled until normal prepare-sso/configure-module acceptance.
The restore credential hook migrates/replays state but never starts the service.
Supported inputs:

- Old cleartext ADMIN_TOKEN: hash the existing token and commit the record.
- Old verified token-file/PHC pair: preserve token and hash exactly.
- Token file with missing ADMIN_TOKEN: derive a hash without changing the token.
- New canonical record plus environment: verify and, if necessary, replay projection.

A legacy hash with a missing/wrong token cannot be recovered cryptographically.
It stays stopped and requires the operator to restore the matching backup or
explicitly rotate. A corrupt canonical record requires recovery from a trusted
backup, not silent replacement. Existing vault data and IdP configuration are
not altered by credential recovery.

An operator-authorized explicit rotation of a readable record or legacy state
can be performed **with the app/timer stopped**, in the module's runagent context:

```python
import agent
import vaultwarden_config as policy
with agent.exclusive_file_lock('configuration'):
    policy.ensure_worker_credential(rotate=True)
    policy.check_worker_credential()
```

Then reset any failed systemd state and restart the app/timer. Do not print the
returned secret/hash. This PR does not perform a production rotation or deploy.
Rollback to older releases is not supported by NS8; old releases do not understand
the canonical record and may rotate/create a legacy file themselves. Forward
migration treats the surviving canonical record as authority again.

## Coverage / acceptance boundary

Units exercise real Argon2 verification, a second actual 77 hook invocation
(with IdP/systemctl seams), wrong hash, missing legacy half, explicit/schema
rotation, canonical corruption, projection corruption, and injected interruption
before/after the environment replace. Backup fixtures copy only the real
state-include allowlist and migrate cleartext, old pair and canonical backups.
The unchanged baseline fails the wrong-pair behavior and unsafe-restart
regressions; the actual 77 hook attempts an unwanted rotation there.

The existing QEMU suite additionally performs a second cluster/update-module,
compares the canonical record, and exercises systemd/worker denial of a valid
but wrong hash followed by recovery. Disposable QEMU is not live acceptance:
a real node and actual session revocation remain Arne's acceptance gate.
