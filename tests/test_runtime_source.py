"""Regression guard for the reviewed upstream 1.37.5 runtime upgrade."""
from pathlib import Path
import re
import os
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RuntimeSourceTests(unittest.TestCase):
    def test_patched_server_source_matches_reviewed_upstream_base(self):
        recipe = (ROOT / 'prototype/vaultwarden/Containerfile').read_text()
        revision = '6ed6921cc2b0e03b4d74189574d2a5e71c512e97'
        source = re.search(r'git fetch --depth=1 origin ([0-9a-f]{40})', recipe)
        self.assertIsNotNone(source)
        assert source is not None
        self.assertEqual(source[1], revision)
        self.assertIn('VW_VERSION=1.37.5-group-prototype', recipe)
        self.assertIn('org.opencontainers.image.version="1.37.5-group-prototype"', recipe)
        self.assertIn(f'org.opencontainers.image.revision="{revision}"', recipe)
        self.assertIn('FROM docker.io/vaultwarden/server@sha256:f8863ab2519364bfc657144006682a830784e0bb501606d5e34516ee76b60b5c', recipe)
        self.assertIn('git apply --check /tmp/deny-api-key.patch && git apply /tmp/deny-api-key.patch', recipe)
        self.assertIn('COPY ns8_admin.rs /src/src/api/ns8_admin.rs', recipe)

    @unittest.skipUnless(os.environ.get('VW_UPSTREAM_SOURCE'), 'set VW_UPSTREAM_SOURCE to pristine 1.37.5 checkout')
    def test_security_patch_applies_without_rejects_to_pinned_source(self):
        upstream = os.environ['VW_UPSTREAM_SOURCE']
        revision = subprocess.check_output(['git', '-C', upstream, 'rev-parse', 'HEAD'], text=True).strip()
        self.assertEqual(revision, '6ed6921cc2b0e03b4d74189574d2a5e71c512e97')
        applied = subprocess.run(['git', '-C', upstream, 'apply', '--check',
            str(ROOT / 'prototype/vaultwarden/deny-api-key-sso-only.patch')], capture_output=True, text=True)
        self.assertEqual(applied.returncode, 0, applied.stderr)


if __name__ == '__main__':
    unittest.main()
