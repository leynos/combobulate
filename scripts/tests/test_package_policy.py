"""Prove the package manifest follows the accepted licence and publication policy (VO-13)."""
from __future__ import annotations

import json
import sys
import tempfile
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

    def test_lifecycle_selects_enforced_rules_and_report(self):
        """Enforce and report exactly the accepted decisions across all four activation states."""
        cases = (
            ('both', ('D04', 'D05'), 'the ISC licence (D04); publish = false (D05)', 2),
            ('licence-only', ('D04',), 'the ISC licence (D04)', 1),
            ('publication-only', ('D05',), 'publish = false (D05)', 1),
            ('neither', (), 'no package rule', 0),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'spec').mkdir()
            for name, accepted, detail, count in cases:
                register = {'decisions': [
                    {'id': decision, 'lifecycle': 'accepted' if decision in accepted else 'proposed'}
                    for decision in ('D04', 'D05')
                ]}
                (root / 'spec/decisions.json').write_text(json.dumps(register), encoding='utf-8')
                for licence, publish in (('ISC', False), ('MIT', False), ('ISC', True), ('MIT', True)):
                    with self.subTest(lifecycle=name, licence=licence, publish=publish):
                        (root / 'Cargo.toml').write_text(
                            f'[package]\nlicense = "{licence}"\npublish = {str(publish).lower()}\n',
                            encoding='utf-8',
                        )
                        context = ValidationContext(root)
                        if 'D04' in accepted and licence != 'ISC':
                            diagnostic = 'license = "ISC"'
                        elif 'D05' in accepted and publish:
                            diagnostic = 'publish = false'
                        else:
                            diagnostic = None
                        if diagnostic is not None:
                            with self.assertRaisesRegex(AssertionError, diagnostic):
                                check_package_policy(context)
                            self.assertEqual(context.results, [], 'a rejected manifest must not record a pass')
                        else:
                            check_package_policy(context)
                            self.assertEqual(context.results, [{
                                'check': 'package-policy', 'status': 'pass', 'count': count,
                                'detail': f'Cargo.toml satisfies the accepted package decisions: {detail}.',
                            }], 'the report must identify exactly the enforced rules and their count')


if __name__ == '__main__':
    unittest.main()
