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
        """Run task-closure validation before package publication policy."""
        context = ValidationContext(ROOT)
        collect_checks(context)
        checks = [row['check'] for row in context.results]
        results = [row for row in context.results if row['check'] == 'package-policy']
        self.assertEqual(len(results), 1,
                         'the composed checker must report the package-policy check exactly once')
        self.assertLess(checks.index('roadmap-status'), checks.index('package-policy'),
                        'package policy must consume validated roadmap closure results')

    def test_decision_lifecycle_controls_manifest_requirements_independently(self):
        """Tie licence enforcement to D04 and fail closed on publication changes."""
        cases = (
            ('accepted D04 rejects another licence', 'accepted', 'proposed', 'MIT', True,
             'license = "ISC"'),
            ('proposed D04 permits another licence', 'proposed', 'accepted', 'MIT', False, None),
            ('accepted D05 blocks publication', 'proposed', 'accepted', 'MIT', True,
             'publish = false'),
            ('proposed D05 keeps publication disabled', 'proposed', 'proposed', 'MIT', True,
             'publish = false'),
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

    def test_accepted_d05_supersession_without_core_closure_keeps_publication_disabled(self):
        """Require task 4.3.3 closure as well as sponsor release approval."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_release_fixture(root, publish=True)
            context = ValidationContext(root)
            with self.assertRaisesRegex(AssertionError, 'publish = false'):
                check_package_policy(context)

    def test_core_closure_without_accepted_d05_supersession_keeps_publication_disabled(self):
        """Do not treat dossier completion by itself as sponsor release approval."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_release_fixture(root, publish=True, supersede_d05=False)
            context = ValidationContext(root)
            self.add_validated_core_closure(context)
            with self.assertRaisesRegex(AssertionError, 'publish = false'):
                check_package_policy(context)

    def test_accepted_d05_supersession_and_validated_core_closure_allow_publication(self):
        """Lift the D05 guard only after both recorded release conditions pass."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_release_fixture(root, publish=True)
            context = ValidationContext(root)
            self.add_validated_core_closure(context)
            check_package_policy(context)
            self.assertEqual(context.results[-1]['check'], 'package-policy',
                             'an approved release must still record a package-policy result')

    @staticmethod
    def write_release_fixture(root: Path, *, publish: bool, supersede_d05: bool = True) -> None:
        """Write the smallest manifest and decision register for D05 release cases."""
        (root / 'spec').mkdir()
        (root / 'Cargo.toml').write_text(
            '[package]\nname = "policy-fixture"\nversion = "0.1.0"\n'
            f'license = "ISC"\npublish = {str(publish).lower()}\n', encoding='utf-8')
        d05 = {'id': 'D05', 'lifecycle': 'superseded' if supersede_d05 else 'accepted',
               'superseded_by': 'D16' if supersede_d05 else None}
        decisions = [
            {'id': 'D04', 'lifecycle': 'accepted'},
            d05,
            {'id': 'D16', 'lifecycle': 'accepted' if supersede_d05 else 'proposed',
             'supersedes': ['D05'] if supersede_d05 else []},
        ]
        (root / 'spec/decisions.json').write_text(json.dumps({'decisions': decisions}), encoding='utf-8')

    @staticmethod
    def add_validated_core_closure(context: ValidationContext) -> None:
        """Model task closure only after the composed roadmap check has passed."""
        (context.root / 'spec/roadmap.json').write_text(json.dumps({
            'phases': [{'steps': [{'tasks': [{'id': '4.3.3', 'status': 'done'}]}]}],
        }), encoding='utf-8')
        (context.root / 'spec/task-completion.json').write_text(
            json.dumps({'tasks': [{'task': '4.3.3'}]}), encoding='utf-8')
        context.record('roadmap-status', 'task 4.3.3 closure conditions pass', 1)

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
