"""Prove the package manifest follows the accepted licence and publication policy (VO-13)."""
from __future__ import annotations

import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_docs import collect_checks
from docs_validation.context import ValidationContext
from docs_validation.package_policy import check_manifest, check_package_policy

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = tomllib.loads((ROOT / 'Cargo.toml').read_text(encoding='utf-8'))


class PackagePolicy(unittest.TestCase):
    """D04 fixes the licence; D05 blocks publication until release is approved."""

    def test_committed_manifest_passes(self):
        """Keep the checked-in package aligned with both accepted decisions."""
        check_package_policy(ValidationContext(ROOT))

    def test_composed_checker_records_package_policy(self):
        """Keep package policy in the repository-wide validation composition."""
        context = ValidationContext(ROOT)
        collect_checks(context)
        results = [row for row in context.results if row['check'] == 'package-policy']
        self.assertEqual(len(results), 1,
                         'the composed checker must report the package-policy check exactly once')

    def test_decision_lifecycle_controls_manifest_requirements_independently(self):
        """Enforce each manifest rule only while its governing decision is accepted."""
        cases = (
            ('accepted D04 rejects another licence', 'accepted', 'proposed', 'MIT', True,
             'license = "ISC"'),
            ('proposed D04 permits another licence', 'proposed', 'proposed', 'MIT', True, None),
            ('accepted D05 blocks publication', 'proposed', 'accepted', 'MIT', True,
             'publish = false'),
            ('proposed D05 permits publication', 'proposed', 'proposed', 'MIT', True, None),
        )
        for label, d04, d05, license_name, publish, expected_error in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'spec').mkdir()
                manifest = ('[package]\nname = "policy-fixture"\nversion = "0.1.0"\n'
                            f'license = "{license_name}"\npublish = {str(publish).lower()}\n')
                (root / 'Cargo.toml').write_text(manifest, encoding='utf-8')
                decisions = {'decisions': [
                    {'id': 'D04', 'lifecycle': d04},
                    {'id': 'D05', 'lifecycle': d05},
                ]}
                (root / 'spec/decisions.json').write_text(json.dumps(decisions), encoding='utf-8')
                context = ValidationContext(root)
                if expected_error is None:
                    check_package_policy(context)
                    self.assertEqual(context.results[0]['check'], 'package-policy',
                                     f'{label} must record a successful package-policy check')
                else:
                    with self.assertRaisesRegex(AssertionError, expected_error):
                        check_package_policy(context)

    def test_publishable_manifest_fails(self):
        """Reject registry publication while the D05 release gate stands."""
        manifest = {'package': MANIFEST['package'] | {'publish': True}}
        with self.assertRaisesRegex(AssertionError, 'publish = false'):
            check_manifest(manifest)

    def test_missing_publish_flag_fails(self):
        """Treat an omitted publication setting as publishable by default."""
        package = {key: value for key, value in MANIFEST['package'].items() if key != 'publish'}
        with self.assertRaisesRegex(AssertionError, 'publish = false'):
            check_manifest({'package': package})

    def test_other_licence_fails(self):
        """Reject a package licence that disagrees with accepted D04."""
        manifest = {'package': MANIFEST['package'] | {'license': 'MIT'}}
        with self.assertRaisesRegex(AssertionError, 'license = "ISC"'):
            check_manifest(manifest)


if __name__ == '__main__':
    unittest.main()
