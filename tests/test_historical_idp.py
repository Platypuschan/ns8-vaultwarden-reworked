"""Keep the manually built historical overlay coherent, not the independent IdP."""
from pathlib import Path
import re
import ast
import io
import importlib.util
import hashlib
from unittest.mock import patch
from typing import Any
import os
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
IDP = ROOT / 'prototype/idp'


class HistoricalIdpRecipeTests(unittest.TestCase):
    def test_cleanup_registers_failed_launch_and_attempts_all_owned_resources(self):
        # Execute the real harness helpers; only the Podman process boundary is stubbed.
        source = ast.parse((ROOT / 'tests/historical_idp/run.py').read_text())
        definitions: list[ast.stmt] = [node for node in source.body
                       if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
        calls = []
        def command(*args, **kwargs):
            calls.append(args)
            if args[:2] == ('podman', 'run'):
                raise RuntimeError('private launch detail')
            return subprocess.CompletedProcess(args, 1 if 'exists' in args else 0)
        owned = {'container': set(), 'volume': set(), 'network': {'owned-network'}}
        namespace: dict[str, Any] = dict(original_cmd=command, owned=owned, unittest=unittest)
        exec(compile(ast.Module(body=definitions, type_ignores=[]), '<harness helpers>', 'exec'), namespace)
        with self.assertRaises(RuntimeError):
            namespace['tracked_cmd']('podman', 'run', '--name', 'owned-container',
                                     '--volume', 'owned-volume:/data', 'unused')
        self.assertEqual(owned['container'], {'owned-container'})
        self.assertEqual(owned['volume'], {'owned-volume'})
        namespace['cleanup']()
        for kind, name in (('container', 'owned-container'), ('volume', 'owned-volume'),
                           ('network', 'owned-network')):
            self.assertIn(('podman', kind, 'exists', name), calls)
        class FailingCase(unittest.TestCase):
            def runTest(self):
                raise RuntimeError('PRIVATE_CREDENTIAL')
        output = io.StringIO()
        result = unittest.TextTestRunner(stream=output, resultclass=namespace['PrivateResult']).run(FailingCase())
        self.assertFalse(result.wasSuccessful())
        self.assertIn('RuntimeError', output.getvalue())
        self.assertNotIn('PRIVATE_CREDENTIAL', output.getvalue())

    def test_complete_python_inventory_rejects_modifications_and_import_shadows(self):
        spec = importlib.util.spec_from_file_location(
            'historical_provenance', ROOT / 'tests/historical_idp/provenance.py')
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # Deliberate inventory seam: test hashing/allowlisting on real files,
        # not claim these tiny fixtures are the pinned upstream source.
        expected = {name: hashlib.sha256(name.encode()).hexdigest()
                    for name in module.PYTHON_SHA256}
        with tempfile.TemporaryDirectory() as directory, patch.object(module, 'PYTHON_SHA256', expected):
            package = Path(directory) / 'imageroot/pypkg'
            package.mkdir(parents=True)
            for name in expected:
                (package / name).write_text(name)
            self.assertEqual(module.verify_python(directory), package)
            for name in expected:
                with self.subTest(changed=name):
                    (package / name).write_text('changed')
                    with self.assertRaisesRegex(SystemExit, 'integrity mismatch'):
                        module.verify_python(directory)
                    (package / name).write_text(name)
            for extra in ('extra.py', 'idpfed.so', 'idpfed.pyc'):
                with self.subTest(extra=extra):
                    (package / extra).touch()
                    with self.assertRaisesRegex(SystemExit, 'integrity mismatch'):
                        module.verify_python(directory)
                    (package / extra).unlink()
            (package / 'kcadmin.py').unlink()
            with self.assertRaisesRegex(SystemExit, 'integrity mismatch'):
                module.verify_python(directory)

    def test_unverified_upstream_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / 'imageroot/pypkg'
            package.mkdir(parents=True)
            (package / 'idpfed.py').write_text("raise SystemExit('UNVERIFIED_IMPORT_EXECUTED')")
            env = dict(os.environ, IDP_UPSTREAM_SOURCE_ROOT=directory,
                       HISTORICAL_IDP_RUNTIME_IMAGE='unused', VW_RUNTIME_IMAGE='unused')
            result = subprocess.run(['python3', str(ROOT / 'tests/historical_idp/run.py')],
                                    env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('historical upstream Python integrity mismatch', result.stderr)
        self.assertNotIn('UNVERIFIED_IMPORT_EXECUTED', result.stderr)

    def test_historical_ci_builds_and_runs_read_only_with_full_history(self):
        path = ROOT / '.github/workflows/historical-idp.yml'
        self.assertTrue(path.is_file(), 'historical recipe has no automated image/behavior coverage')
        workflow = path.read_text()
        for required in ('contents: read', 'fetch-depth: 0', 'persist-credentials: false',
                         'paths:', 'prototype/idp/**', 'tests/historical_idp/**',
                         'tests/integration/**', 'runtime-cache.json',
                         'tests/historical_idp/ci.sh'):
            self.assertIn(required, workflow)
        self.assertNotIn('packages: write', workflow)
        script = (ROOT / 'tests/historical_idp/ci.sh').read_text()
        for required in ('prototype/idp/Containerfile', 'image_checks.py', 'historical_idp/run.py',
                         'Samba.Containerfile', '.github/scripts/runtime-tag', 'sha256sum -c',
                         'podman pull', 'runtime-cache.json'):
            self.assertIn(required, script)
        self.assertNotRegex(script, r'podman (push|login)')

    def test_runtime_matches_provided_spi_version(self):
        pom = ET.parse(IDP / 'pom.xml')
        version = pom.findtext('{*}properties/{*}keycloak.version')
        recipe = (IDP / 'Containerfile').read_text()
        runtime = re.search(r'^FROM quay.io/keycloak/keycloak:([^@]+)@sha256:[0-9a-f]{64}$',
                            recipe, re.MULTILINE)
        self.assertIsNotNone(runtime, 'historical SPI update needs a matching immutable runtime')
        assert runtime is not None
        self.assertEqual(runtime[1], version)
        self.assertIn('verify-runtime.sh', recipe, 'build must verify actual runtime, not just its tag')


if __name__ == '__main__':
    unittest.main()
