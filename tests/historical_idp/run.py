#!/usr/bin/env python3
"""Run the last historical overlay protocol fixture, not today's independent IdP.

Requires full repository history, IDP_UPSTREAM_SOURCE_ROOT (upstream 433fa069),
HISTORICAL_IDP_RUNTIME_IMAGE and VW_RUNTIME_IMAGE; creates disposable containers.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
from typing import Any
import sys

from provenance import verify_python

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = '4862c791adf50fae5f3cd7ed6dc371272147e368:tests/integration/run.py'
# Validate external input before consulting optional fixture history. Ordinary
# unit discovery must reject poison even in a shallow production CI checkout.
upstream = verify_python(Path(os.environ['IDP_UPSTREAM_SOURCE_ROOT']).resolve())
source = subprocess.check_output(['git', '-C', str(ROOT), 'show', FIXTURE], text=True)
image = os.environ['HISTORICAL_IDP_RUNTIME_IMAGE']
os.environ['VW_RUNTIME_IMAGE']  # No implicit/reused production runtime.
assert (upstream / 'idpfed.py').is_file(), 'need the historical upstream source'


def assert_token_lifespan(case, token, expected):
    # expires_in is remaining time at response construction, not the configured
    # lifetime. LDAP/provider work can cross a wall-clock second after issuance.
    # Check the issued lifetime exactly, while bounding response age as in the
    # current protocol suite. Claims come from our disposable loopback IdP;
    # decoding here is an assertion, not application token authentication.
    payload = token['access_token'].split('.')[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    case.assertEqual(claims['exp'] - claims['iat'], expected)
    case.assertGreaterEqual(token['expires_in'], expected - 5)
    case.assertLessEqual(token['expires_in'], expected)


replacements = {
    "        self.assertEqual(token['expires_in'],600)":
        '        assert_token_lifespan(self, token, 600)',
    'ROOT = Path(__file__).resolve().parents[2]': f'ROOT = Path({str(ROOT)!r})',
    "sys.path.insert(0, str(ROOT / 'tests/integration/upstream'))":
        f'sys.path.append({str(upstream)!r})',
    "'localhost/ns8-idp-group-prototype'": repr(image),
    "'localhost/ns8-vaultwarden-test-samba'": repr(os.environ.get(
        'HISTORICAL_SAMBA_IMAGE', 'localhost/ns8-vaultwarden-test-samba')),
}
for old, new in replacements.items():
    assert source.count(old) == 1, 'historical fixture seam changed'
    source = source.replace(old, new)
# Preserve the protocol/security checks, correcting only the distinction between
# issued and remaining token lifetime above. Own cleanup without retaining logs.
# The immutable fixture's old cleanup filtered strings from logs; do not rely
# on a denylist to keep arbitrary credentials out of artifacts.
namespace: dict[str, Any] = {'__name__': 'historical_fixture', '__file__': __file__,
                             'assert_token_lifespan': assert_token_lifespan}
exec(compile(source, FIXTURE, 'exec'), namespace)
original_cmd = namespace['cmd']
owned = {'container': set(), 'volume': set(), 'network': set()}


def tracked_cmd(*args, **kwargs):
    if args[:2] == ('podman', 'run'):
        if '--name' in args:
            owned['container'].add(args[args.index('--name') + 1])
        if '--volume' in args:
            owned['volume'].add(args[args.index('--volume') + 1].split(':')[0])
    elif args[:3] == ('podman', 'network', 'create'):
        owned['network'].add(args[3])
    return original_cmd(*args, **kwargs)


def cleanup(*_):
    failed = []
    for kind, names in owned.items():
        for name in sorted(names):
            command = ('podman', 'rm', '-f', name) if kind == 'container' else (
                'podman', kind, 'rm', name)
            original_cmd(*command, check=False)
            result = original_cmd('podman', kind, 'exists', name, check=False)
            if result.returncode != 1:
                failed.append(kind)  # Never include potentially sensitive command output.
    if failed:
        raise RuntimeError('historical fixture cleanup could not confirm owned resource absence')


namespace['cmd'] = tracked_cmd
case = namespace['LoginTests']
case.cleanup = classmethod(cleanup)
unittest = namespace['unittest']
suite = unittest.defaultTestLoader.loadTestsFromTestCase(case)
assert suite.countTestCases() == 16, 'historical fixture test inventory changed'
class PrivateResult(unittest.TextTestResult):
    def _exc_info_to_string(self, err, test):
        # Failure details may contain LDAP passwords, redirect codes or tokens.
        # Keep only trusted immutable-fixture line numbers, never source, locals,
        # arbitrary paths, or exception text. This identifies the leaf assertion.
        lines = []
        tb = err[2]
        while tb is not None:
            if tb.tb_frame.f_code.co_filename == FIXTURE:
                lines.append(str(tb.tb_lineno))
            tb = tb.tb_next
        return err[0].__name__ + (' fixture-lines=' + ','.join(lines) if lines else '')


try:
    result = unittest.TextTestRunner(verbosity=2, resultclass=PrivateResult).run(suite)
finally:
    cleanup()
if result.testsRun != 16 or result.skipped or not result.wasSuccessful():
    raise SystemExit(1)
