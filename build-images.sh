#!/bin/bash
set -Eeuo pipefail
base="${REPOBASE:-ghcr.io/platypuschan}"
tag="${IMAGETAG:-$(cat VERSION)}"
buildah bud --layers -t "$base/vaultwarden-reworked-server:$tag" -f prototype/vaultwarden/Containerfile prototype/vaultwarden
buildah bud --layers -t "$base/vaultwarden-reworked:$tag" --build-arg "VAULTWARDEN_IMAGE=$base/vaultwarden-reworked-server:$tag" -f Containerfile .
if [[ -n "${CI:-}" ]]; then
    printf 'images=%s\n' "$base/vaultwarden-reworked-server $base/vaultwarden-reworked" >> "$GITHUB_OUTPUT"
fi
