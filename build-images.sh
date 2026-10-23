#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -Eeuo pipefail
repobase="${REPOBASE:-ghcr.io/platypuschan}"
tag="${IMAGETAG:-codex-vaultwarden-sso}"
# All images belong to this prototype branch, never to a stable catalog.
buildah bud --layers -t "${repobase}/idp-keycloak" -f prototype/idp/Containerfile prototype/idp
buildah bud --layers -t "${repobase}/idp-vaultwarden-prototype" \
    --build-arg "KEYCLOAK_IMAGE=${repobase}/idp-keycloak:${tag}" -f prototype/idp/Module.Containerfile .
buildah bud --layers -t "${repobase}/vaultwarden" -f Containerfile .
images="${repobase}/idp-keycloak ${repobase}/idp-vaultwarden-prototype ${repobase}/vaultwarden"
if [[ -n "${CI:-}" ]]; then
    printf 'images=%s\n' "${images}" >>"${GITHUB_OUTPUT}"
else
    printf '%s\n' "Built local prototype images: ${images}"
fi
