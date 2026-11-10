# UI dependency audit (2026-11-10)

Node 24.22.2, Yarn 4.18.1. Scope: dependency resolutions and regression
coverage only; Vue 2.7, Carbon 10 and the patched application runtime stay intact.
This repository releases from `VERSION` (0.1.4 -> 0.1.5), not CATALOG_VERSION.

## Reproduce

```sh
yarn install --immutable
yarn explain peer-requirements
yarn lint
yarn build # includes dependency consumer regression tests
yarn npm audit --all --recursive
```

The audit includes deprecation notices: before, 19 entries (7 high, 10 moderate,
2 low); after, 7 entries (6 moderate deprecations and the low Vue 2 ReDoS
GHSA-5j4c-8p2g-v4jx). A nonzero audit exit remains expected; it is NOT suppressed.
There are no high findings in the recorded post-change audit. Registry advisories
can change; this is a snapshot, not a permanent zero-vulnerability assertion.

## Fixed build/tooling dependencies

Targeted parent/child resolutions avoid unrelated dependency changes:

- `flat-cache/flatted`: 2.0.2 -> 3.4.4; fixes GHSA-25h7-pfq9-p65f and
  GHSA-rf6f-7fwh-wjgh. Test the actual flat-cache cyclic save/reload API.
- `external-editor/tmp`: 0.0.33 -> 0.2.7; fixes GHSA-52f5-9888-hmc6 and
  GHSA-ph9p-34f9-6g65. Test the actual editor temporary-file create/cleanup API.
- `node-gyp/undici`: 8.11.2 -> 8.12.4; fixes eight audit entries, including
  TLS-validation bypass, redirect disclosure and several denial-of-service issues.
  Test node-gyp's resolved request API against a disposable local HTTP server.

All three version guards failed with the original lockfile before their fixes.
`yarn build` executes these tests, so existing production, PR and release image
builds exercise them without introducing a separate unexercised CI path.

## Deliberately retained warnings and dependencies

Inspect both `src/` and the installed `@nethserver/ns8-ui-lib` before removal:

- `lottie-web-vue` is imported by the library's `NsLottieAnimation`, consumed by
  `NsEmptyState`/`NsDataTable`. Keep it and the visible lottie-web eval warning;
  removing the app registration alone would not remove the imported library.
- `vue-axios` supplies `this.axios`, used by the library's task transport.
- `vue-debounce` registers `v-debounce`, used by `NsDataTable` and
  `NsComboSearchBox`. Keep the plugin registration.
- ESLint 6 satisfies eslint-plugin-vue 6 but not @babel/eslint-parser 7's peer
  range. No fake package extension hides this incompatible peer requirement.
  A coordinated lint-toolchain migration is outside this dependency-only fix.
- ns8-ui-lib ships build-time @rollup/plugin-json as a production dependency,
  whose Rollup peer is missing. The application doesn't execute the library's
  Rollup build. Installing a second bundler or falsifying metadata merely to
  silence that packaging warning is not required here.
- No VueUse dependency or peer warning is present. No minimatch advisory is
  reported by this audit (installed minimatch 3.1.5); do not replace the legacy
  callable CommonJS API with minimatch 11 speculatively.
- `/cluster-admin/css/core.css` is intentionally supplied by the NS8 host at
  runtime. Its build-time missing-file notice remains. No CJS/ESM warning was
  observed. No warning filters or audit ignores were added.
- Remaining deprecations: carbon-components, eslint, glob, inflight, rimraf,
  vue-i18n. Fixing the Vue ReDoS or removing Carbon 10 requires a separately
  scoped stack migration, not a compatible dependency resolution.

Runtime recipe, cache hash, runtime image pin, IdP pins and application source
are unchanged. The runtime is reused by the release workflow, not rebuilt.
