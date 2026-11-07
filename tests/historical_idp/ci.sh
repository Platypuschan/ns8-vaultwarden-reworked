#!/bin/bash
# Read-only registry access; no credentials, publication or production changes.
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
[[ $(git rev-parse --is-shallow-repository) == false ]]
scratch=$(mktemp -d)
token=${scratch##*/}
export HISTORICAL_IDP_RUNTIME_IMAGE="localhost/vw-historical-idp-${token,,}"
export HISTORICAL_SAMBA_IMAGE="localhost/vw-historical-samba-${token,,}"
cleanup() {
    local failed=0 status
    for image in "$HISTORICAL_IDP_RUNTIME_IMAGE" "$HISTORICAL_SAMBA_IMAGE"; do
        podman image rm "$image" >/dev/null 2>&1 || true
        status=0
        podman image exists "$image" || status=$?
        if [[ $status != 1 ]]; then
            printf 'Owned historical fixture image cleanup failed\n' >&2
            failed=1
        fi
    done
    rm -rf "$scratch"
    return "$failed"
}
trap cleanup EXIT
# Verify the current checkout's cache recipe and immutable runtime pin. Never
# silently rebuild or fall back to an unrelated application runtime.
[[ $(.github/scripts/runtime-tag) == "$(python3 -c 'import json; print(json.load(open("runtime-cache.json"))["recipe"])')" ]]
export VW_RUNTIME_IMAGE
VW_RUNTIME_IMAGE=$(python3 -c 'import json; print(json.load(open("runtime-cache.json"))["image"])')
[[ $VW_RUNTIME_IMAGE =~ ^ghcr.io/platypuschan/vaultwarden-reworked-server@sha256:[0-9a-f]{64}$ ]]
podman pull "$VW_RUNTIME_IMAGE"
podman run --rm --network=none --entrypoint /vaultwarden "$VW_RUNTIME_IMAGE" --version
# Use precisely the archive/checksum from the historical recipe. The Python
# inventory is checked again before importing any extracted upstream module.
curl --fail --location --retry 3 \
    https://api.github.com/repos/NethServer/ns8-idp/tarball/433fa069c2eab4c073303769ac84c40b37a2676b \
    -o "$scratch/upstream.tar.gz"
printf '%s  %s\n' afc529321020a4f20eb44f5552738e1cf3ca68416d10ad70c1688677800f87c3 "$scratch/upstream.tar.gz" | sha256sum -c -
mkdir "$scratch/upstream"
tar -xzf "$scratch/upstream.tar.gz" -C "$scratch/upstream" --strip-components=1
export IDP_UPSTREAM_SOURCE_ROOT="$scratch/upstream"
podman build -t "$HISTORICAL_IDP_RUNTIME_IMAGE" -f prototype/idp/Containerfile prototype/idp
python3 tests/historical_idp/image_checks.py
podman build -t "$HISTORICAL_SAMBA_IMAGE" -f tests/integration/Samba.Containerfile tests/integration
python3 tests/historical_idp/run.py
