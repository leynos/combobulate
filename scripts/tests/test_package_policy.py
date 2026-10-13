"""Prove the package manifest follows the accepted licence and publication policy (VO-13)."""
from __future__ import annotations

import sys
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.package_policy import check_manifest, check_package_policy

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = tomllib.loads((ROOT / 'Cargo.toml').read_text(encoding='utf-8'))


class PackagePolicy(unittest.TestCase):
    """D04 fixes the licence; D05 blocks publication until release is approved."""

    def test_committed_manifest_passes(self):
        check_package_policy(ValidationContext(ROOT))

    def test_publishable_manifest_fails(self):
        manifest = {'package': MANIFEST['package'] | {'publish': True}}
        with self.assertRaisesRegex(AssertionError, 'publish = false'):
            check_manifest(manifest)

    def test_missing_publish_flag_fails(self):
        package = {key: value for key, value in MANIFEST['package'].items() if key != 'publish'}
        with self.assertRaisesRegex(AssertionError, 'publish = false'):
            check_manifest({'package': package})

    def test_other_licence_fails(self):
        manifest = {'package': MANIFEST['package'] | {'license': 'MIT'}}
        with self.assertRaisesRegex(AssertionError, 'license = "ISC"'):
            check_manifest(manifest)


if __name__ == '__main__':
    unittest.main()
