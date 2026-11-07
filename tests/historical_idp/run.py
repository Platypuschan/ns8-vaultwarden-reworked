#!/usr/bin/env python3
"""Run the last historical overlay protocol fixture, not today's independent IdP.

Requires full repository history, IDP_UPSTREAM_SOURCE_ROOT (upstream 433fa069),
HISTORICAL_IDP_RUNTIME_IMAGE and VW_RUNTIME_IMAGE; creates disposable containers.
"""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = '4862c791adf50fae5f3cd7ed6dc371272147e368:tests/integration/run.py'
source = subprocess.check_output(['git', '-C', str(ROOT), 'show', FIXTURE], text=True)
upstream = Path(os.environ['IDP_UPSTREAM_SOURCE_ROOT']).resolve() / 'imageroot/pypkg'
image = os.environ['HISTORICAL_IDP_RUNTIME_IMAGE']
os.environ['VW_RUNTIME_IMAGE']  # No implicit/reused production runtime.
assert (upstream / 'idpfed.py').is_file(), 'need the historical upstream source'
replacements = {
    'ROOT = Path(__file__).resolve().parents[2]': f'ROOT = Path({str(ROOT)!r})',
    "sys.path.insert(0, str(ROOT / 'tests/integration/upstream'))":
        f'sys.path.append({str(upstream)!r})',
    "'localhost/ns8-idp-group-prototype'": repr(image),
}
for old, new in replacements.items():
    assert source.count(old) == 1, 'historical fixture seam changed'
    source = source.replace(old, new)
# Keep the original assertions and historical overlay imports unchanged.
exec(compile(source, FIXTURE, 'exec'), globals())
