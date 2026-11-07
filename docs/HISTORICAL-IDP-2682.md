# Historical IdP overlay: coherent Keycloak 26.8.2

This recipe is **not** the production independent `ns8-idp-reworked` runtime.
PR27 originally updated only the `provided` SPI dependencies to 26.8.2 while
`ghcr.io/nethserver/idp-keycloak@sha256:68b73b4f5130609fbc69fdc89cf493b0e9ee2edbad271e3bb640b03b113a996d`
actually runs 26.7.4. A successful Maven build cannot validate that mismatch.

## Runtime and original NS8 features

Public registry inspection on 2026-11-07 found no matching 26.8.2 NS8 base:
`main`, `latest`, `renovate-patch-keycloak`, `renovate-keycloak` all advertised
26.7.4. Rather than discard the NS8 providers or revert the requested upgrade,
the recipe narrowly rebuilds the historical upstream providers alongside the
access-policy overlay, against the same POM-derived 26.8.2 SPI version:

- Original upstream source: [NethServer/ns8-idp at 433fa069c2eab4c073303769ac84c40b37a2676b](https://github.com/NethServer/ns8-idp/tree/433fa069c2eab4c073303769ac84c40b37a2676b).
  Its API tarball is SHA256-verified before extraction. No upstream Java,
  mapper scripts or healthcheck are edited. Rebuild `ns8-authenticators.jar`,
  repackage `ns8-mappers.jar`, retain executable `ns8-healthcheck`.
- Runtime: `quay.io/keycloak/keycloak:26.8.2@sha256:3879c623248408de29a5303178b5816c77e8dfef3890c361f8c0bbeaa979ba3b`.
  Verified raw OCI index hash; linux/amd64 child is
  `sha256:4340d05ee7d15be34293868d495ac772d61f1a4d0e43d53bae2e75e2f05de185`.
  The index also supports arm64/ppc64le, but only amd64 was executed here.
- Keep postgres/scripts/health/local-cache settings, nonroot user1000 and
  `kc.sh start --optimized` defaults from the NS8 base. Augment all three
  providers together; do not copy 26.7.4 Quarkus augmentation into 26.8.2.
- `verify-runtime.sh` fails the build unless the **executed** Keycloak version
  and five actual core/SPI JAR filenames match the POM, all three NS8 JARs
  exist, and the NS8 healthcheck is executable.

A new upstream archive checksum, base digest or SPI bump needs review and a
new image build. Archive regeneration fails closed rather than bypassing
integrity checking. Maven remains the previously accepted 3.10/Java21 builder.

## Consumers and scope

The direct consumer is the manual historical build in `docs/TESTING.md`.
`prototype/idp/Module.Containerfile` declares a separately published historical
runtime; changing this recipe does **not** republish or retarget that module.
`.github/workflows/ns8-prototype.yml` is a disabled notice-only workflow.
Current `prerelease.yml`, protocol tests and NS8 tests obtain the independent
IdP through `IDP_REF`/`IDP_IMAGE`/`IDP_SOURCE_ROOT`/`IDP_RUNTIME_IMAGE`. They do
not exercise this recipe. The separate `historical-idp.yml` workflow now
builds this exact recipe and Samba fixture and runs all image guards plus the
historical 16-case behavior suite for path-filtered pushes/PRs (including
runtime-cache/recipe and fixture dependencies), or manual dispatch. It has
only top-level `contents: read`, full-history checkout, no persisted checkout
credentials, registry login, package writes or publication. No production
cache, module default or independent IdP source is changed by this fix.

## Reproduce

From a full-history Vaultwarden checkout, with Podman and Python `requests`:

```sh
podman build --pull=always --no-cache \
  -t localhost/vw-historical-idp-2682 \
  -f prototype/idp/Containerfile prototype/idp
python -m unittest discover -s tests -p test_historical_idp.py -v
HISTORICAL_IDP_RUNTIME_IMAGE=localhost/vw-historical-idp-2682 \
  python tests/historical_idp/image_checks.py
```

For historical behavioral acceptance, extract the same verified upstream
source archive used in the recipe to a private scratch directory. Build the
Samba fixture with `tests/integration/Samba.Containerfile`, retaining the
existing local name `localhost/ns8-vaultwarden-test-samba`. Supply an actual
SSO-only patched Vaultwarden runtime (no implicit runtime default):

```sh
IDP_UPSTREAM_SOURCE_ROOT=/absolute/path/to/extracted/ns8-idp \
HISTORICAL_IDP_RUNTIME_IMAGE=localhost/vw-historical-idp-2682 \
VW_RUNTIME_IMAGE=localhost/your-tested-vaultwarden-runtime \
  python tests/historical_idp/run.py
```

The runner verifies the **complete** upstream `imageroot/pypkg` inventory
(`idpfed.py`, `idprealm.py`, `kcadmin.py`) against hashes derived from that
SHA256-verified archive **before** executing/importing the fixture. Missing,
modified or extra entries, symlinks, bytecode and native import shadows fail
closed. Use a freshly extracted source tree; bytecode is disabled during the
run. The overlay's `idprealm.py` and the fixture's NS8 import stubs remain the
original declared seams, not replacements for upstream provenance.

The runner loads the last historical 16-case fixture directly from immutable
Git object `4862c791adf50fae5f3cd7ed6dc371272147e368`, substituting source
paths and isolated IdP/Samba image names. Authentication and revocation assertions
are retained. One timing assertion is corrected: the issued access-token lifetime
must be exactly 600 seconds (`exp - iat`), while `expires_in` may be 595–600
seconds because response construction can cross a wall-clock second. Regression
tests reject an incorrect issued lifetime and out-of-range remaining TTL. Safe
failure diagnostics retain immutable fixture line numbers, never token values or
exception text. The harness requires exactly 16 executed successes without skips,
registers owned resources before launch, attempts cleanup and verifies their
absence, and does not save container logs. Failures report exception classes
without secret-bearing exception text. It uses actual Samba/LDAP, Keycloak
and Vaultwarden; NS8 agent library imports are stubbed exactly as in the
original protocol fixture. This is not an NS8 agent/QEMU lifecycle or
production deployment test.

For the complete CI-equivalent run (Podman, curl and requests installed):

```sh
bash tests/historical_idp/ci.sh
```

This downloads and checksum-verifies the pinned archive, verifies the current
Vaultwarden recipe equals `runtime-cache.json`, requires its immutable digest
pin, pulls it anonymously and executes its version command. It never writes
the runtime cache or rebuilds Vaultwarden. Unique local image tags and scratch
source are removed on exit; registry access is pull-only.

## Review hardening acceptance (2026-11-07)

- RED/GREEN: missing historical CI regression; provider-negative assertion
  initially failed on the old guard's empty diagnostic; poisoned upstream
  `idpfed.py` initially executed before the new integrity check. An additional
  RED/GREEN regression caught a native import-shadow entry. Broken version
  input cannot satisfy the exact missing-provider denial assertion.
- Updated guard rebuilt/augmented in the actual image; Maven provider layers
  reused. Result image ID
  `41295558ae45113a9b721f5121fd84ce8e83630754bf6f60949fae5530fac3f7`.
- Full local CI-equivalent script: PASS, **4/4** actual image checks (three
  original guards plus broken-input negative control), **16/16** historical
  behavioral tests in 84.434s, cleanup confirmed. It used the checkout's
  verified published Vaultwarden cache pin
  `sha256:0d0332fa274b3d12f30c82611735a72cd2bb30a17c9bc1dd0b90d96d3cafadf0`;
  executed Vaultwarden1.37.5-group-prototype / Web-Vault2026.10.1.
- Full unit suite with pristine1.37.5 source: **47/47 PASS**, zero skips.
  Syntax/diff checks and actionlint1.7.12 for the new workflow: PASS.
  Hosted GitHub execution is not claimed by this local verification.

## Original executed acceptance (2026-11-07)

- RED: new recipe alignment regression failed against exact PR27 on main95249de.
- GREEN: source regression, full unit discovery (43 run: 42 pass, one unrelated
  `VW_UPSTREAM_SOURCE`-gated patch-apply check skipped), Python/JSON/shell syntax.
- No-cache recipe build succeeded, including both Maven provider builds and
  Quarkus augmentation. Local image ID
  `544a78703d7b7220195a97c42fa8e65a9398a4cb603dfe4e732d17480337b905`.
  Executed runtime: Keycloak26.8.2, Red Hat JVM21.0.13.
- Three real-image guard tests pass: accepted matching built runtime; rejected
  original PR27's actual 26.7.4 base with 26.8.2 expectation; rejected runtime
  with providers removed (the vanilla-base regression).
- Historical protocol fixture: **16/16 PASS**, both exploratory replay and
  committed runner. Vaultwarden runtime used was
  `localhost/ns8-vw-pr20-coherent-runtime:1.37.5`.
  Coverage includes allowed/denied users, unrestricted other client,
  mobile/PKCE/password/API-key denial, real SSO-cookie reuse after group
  removal, code/refresh denial, LDAP outage, cached revocation/regrant,
  writable federation and brokered login using the original NS8 providers,
  optional token lifespan, removal/recreation, reconciliation and first
  prototype migration. This explicitly preserves historical broker support;
  it does not reintroduce it into today's LDAP-only independent IdP.

No newly discovered Java behavioral bug required changing the historical
policy implementation. Internal-SPI/preview-feature/deprecated-broker warnings
remain visible; passing augmentation alone was not treated as acceptance.
No remote write, registry publication, merge, named release or user deployment.
Not tested: historical module/NS8 lifecycle, real Entra service, PostgreSQL
upgrade/migration, cross-architecture execution, browser/physical clients.
