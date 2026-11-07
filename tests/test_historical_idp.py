"""Keep the manually built historical overlay coherent, not the independent IdP."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
IDP = ROOT / 'prototype/idp'


class HistoricalIdpRecipeTests(unittest.TestCase):
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
