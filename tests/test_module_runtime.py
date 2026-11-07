"""Keep bare module builds on the recipe-verified CI runtime."""
import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ModuleRuntimeTests(unittest.TestCase):
    def test_bare_module_runtime_label_matches_current_verified_recipe(self):
        cache = json.loads((ROOT / 'runtime-cache.json').read_text())
        recipe = subprocess.check_output(
            ['bash', '.github/scripts/runtime-tag'], cwd=ROOT, text=True
        ).strip()
        self.assertEqual(cache['recipe'], recipe,
                         'Runtime cache is stale; verify the current recipe first')
        self.assertRegex(cache['image'], r'^ghcr\.io/platypuschan/'
                         r'vaultwarden-reworked-server@sha256:[0-9a-f]{64}$')
        containerfile = (ROOT / 'Containerfile').read_text()
        default = re.search(r'^ARG VAULTWARDEN_IMAGE=(\S+)$', containerfile, re.M)
        if default is None:
            self.fail('Bare builds need a verified runtime default')
        label = re.search(r'org\.nethserver\.images="([^"]+)"', containerfile)
        if label is None:
            self.fail('Module must declare its runtime dependency')
        bare_label = label.group(1).replace('${VAULTWARDEN_IMAGE}', default.group(1))
        self.assertEqual(bare_label, cache['image'])


if __name__ == '__main__':
    unittest.main()
