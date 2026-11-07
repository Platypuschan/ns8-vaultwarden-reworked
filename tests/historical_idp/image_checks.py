#!/usr/bin/env python3
"""Explicit real-image acceptance of the historical runtime guard (Podman)."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
IMAGE = os.environ['HISTORICAL_IDP_RUNTIME_IMAGE']
OLD = 'ghcr.io/nethserver/idp-keycloak@sha256:68b73b4f5130609fbc69fdc89cf493b0e9ee2edbad271e3bb640b03b113a996d'


class RuntimeGuardTests(unittest.TestCase):
    def run_guard(self, image, mounts=()):
        return subprocess.run(['podman', 'run', '--rm', '--network=none', '--read-only',
                               *mounts, '--entrypoint', '/bin/bash', image,
                               '/opt/keycloak/bin/ns8-verify-runtime'],
                              capture_output=True, text=True)

    def test_new_runtime_has_matching_spi_and_all_ns8_providers(self):
        result = self.run_guard(IMAGE)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_original_pr27_runtime_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            version = Path(directory) / 'version'
            version.write_text('26.8.2')
            result = self.run_guard(OLD, [
                '-v', f'{version}:/opt/keycloak/conf/ns8-keycloak-version:ro',
                '-v', f'{ROOT}/prototype/idp/verify-runtime.sh:/opt/keycloak/bin/ns8-verify-runtime:ro',
            ])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('runtime/SPI mismatch: expected 26.8.2, got Keycloak 26.7.4', result.stderr)

    def test_vanilla_runtime_without_ns8_providers_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o755)
            result = self.run_guard(IMAGE, ['-v', f'{directory}:/opt/keycloak/providers:ro'])
        self.assert_provider_denial(result, 'ns8-authenticators')

    def assert_provider_denial(self, result, provider):
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(), f'NS8 provider missing or empty: {provider}.jar')

    def test_broken_guard_input_is_not_a_provider_denial(self):
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o755)
            result = self.run_guard(IMAGE, [
                '-v', f'{directory}:/opt/keycloak/conf/ns8-keycloak-version:ro',
            ])
        self.assertNotEqual(result.returncode, 0)
        with self.assertRaises(AssertionError):
            self.assert_provider_denial(result, 'ns8-authenticators')


if __name__ == '__main__':
    unittest.main(verbosity=2)
