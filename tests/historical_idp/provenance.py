"""Inventory derived from the SHA256-verified 433fa069 upstream API archive.

Cover the complete imageroot/pypkg Python set, not only the first imported file.
Do not regenerate hashes from an unverified working directory.
"""
import hashlib
from pathlib import Path

UPSTREAM_COMMIT = '433fa069c2eab4c073303769ac84c40b37a2676b'
ARCHIVE_SHA256 = 'afc529321020a4f20eb44f5552738e1cf3ca68416d10ad70c1688677800f87c3'
PYTHON_SHA256 = {
    'idpfed.py': 'e4abfa00e1d6653167ab5ad8d528f74abbbbaa779c3a7001cd970fc5d7e2766c',
    'idprealm.py': '79f239340625bf010c231c217a58a6bb97778b25fd23115545390b57900e477c',
    'kcadmin.py': 'b01fd32fe6ff2c087b166f6ac7da984503fb850befa23b817aa4f2c9bd3067f1',
}


def verify_python(root):
    package = Path(root) / 'imageroot/pypkg'
    entries = list(package.rglob('*'))
    actual = {p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in entries if p.is_file()}
    # Reject symlinks and every extra entry (including pyc/native import shadows).
    if actual != PYTHON_SHA256 or any(p.is_symlink() or p.is_dir() for p in entries):
        raise SystemExit('historical upstream Python integrity mismatch')
    return package
