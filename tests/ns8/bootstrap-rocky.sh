#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# CI only: provision the core using signed official Rocky packages while the
# NethServer mirror advertises missing metadata (HTTP 404, 2026-10-31).
set -Eeuo pipefail
leader="${1:?missing QEMU guest}"
image="${2:?missing candidate image}"
[[ "$leader" =~ ^[0-9.]+$ ]] || exit 64
[[ "$image" == ghcr.io/platypuschan/vaultwarden-reworked:candidate-* ]] || exit 64
ssh ns8 'bash -s' <<'GUEST'
set -Eeuo pipefail
cd /root
curl -fsSL --retry 3 -o install.sh https://raw.githubusercontent.com/NethServer/ns8-core/cc056a5378a68a3e48ca8e49a1c3643c5cae3ced/core/install.sh
printf '%s\n' '89cf56f5f1e2268ce3a0d092131020b09957744397cb23927bfe2aaabc677def  install.sh' | sha256sum -c -
# Change only package locations and their key source; keep gpgcheck=1.
python3 - <<'PY'
from pathlib import Path
p = Path('install.sh')
s = p.read_text()
for repo in ('BaseOS', 'AppStream'):
    old = 'mirrorlist=http://mirrorlist.nethserver.org/rockylinux?arch=$basearch&repo=' + repo + '-$releasever$rltype'
    assert s.count(old) == 1
    s = s.replace(old, 'baseurl=https://dl.rockylinux.org/pub/rocky/$releasever/' + repo + '/$basearch/os/')
old = 'gpgkey=http://mirrorlist.nethserver.org/rpm-gpg-key-ns8'
assert s.count(old) == 2
s = s.replace(old, 'gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-Rocky-9')
p.write_text(s)
PY
bash install.sh ghcr.io/nethserver/core:3.23.2
GUEST
ssh ns8 "create-cluster ${leader}:55820 10.5.4.0/24 Nethesis,1234"
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec bash "$root/test-module-install.sh" "$leader" "$image"
