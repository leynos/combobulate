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
from docs_validation.revision_reader import git_head_revision

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = tomllib.loads((ROOT / 'Cargo.toml').read_text(encoding='utf-8'))


class PackagePolicy(unittest.TestCase):
    """D04 fixes the licence; D05 blocks publication until release is approved."""

    def test_committed_manifest_passes(self):
        """Keep the checked-in package aligned with both accepted decisions."""
        check_package_policy(ValidationContext(ROOT))

    def test_composed_checker_records_package_policy(self):
        """Run task-closure validation before package publication policy."""
        context = ValidationContext(ROOT, source_revision=git_head_revision(ROOT))
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

    def test_invalid_d05_supersession_links_keep_publication_disabled(self):
        """Reject missing, unknown, and proposed D05 replacement links."""
        cases = (
            ('unknown replacement', 'D99', 'accepted', ['D05']),
            ('missing reciprocal link', 'D16', 'accepted', None),
            ('unknown reciprocal target', 'D16', 'accepted', ['D99']),
            ('proposed replacement', 'D16', 'proposed', ['D05']),
        )
        for label, superseded_by, lifecycle, reciprocal_link in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.write_release_fixture(root, publish=True)
                decision_path = root / 'spec/decisions.json'
                records = json.loads(decision_path.read_text(encoding='utf-8'))['decisions']
                d05 = next(record for record in records if record['id'] == 'D05')
                replacement = next(record for record in records if record['id'] == 'D16')
                d05['superseded_by'] = superseded_by
                replacement['lifecycle'] = lifecycle
                if reciprocal_link is None:
                    replacement.pop('supersedes')
                else:
                    replacement['supersedes'] = reciprocal_link
                decision_path.write_text(json.dumps({'decisions': records}), encoding='utf-8')
                context = ValidationContext(root)
                self.add_validated_core_closure(context)

                with self.assertRaisesRegex(AssertionError, 'publish = false'):
                    check_package_policy(context)

    def test_completed_core_dossier_without_passed_roadmap_check_stays_unpublished(self):
        """Require a passing roadmap check even when task 4.3.3 is recorded done."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_release_fixture(root, publish=True)
            context = ValidationContext(root)
            self.write_core_completion(context)

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

    def write_core_completion(self, context: ValidationContext) -> None:
        """Model task 4.3.3 and its completion record without checker results."""
        (context.root / 'spec/roadmap.json').write_text(json.dumps({
            'phases': [{'steps': [{'tasks': [{'id': '4.3.3', 'status': 'done'}]}]}],
        }), encoding='utf-8')
        (context.root / 'spec/task-completion.json').write_text(
            json.dumps({'tasks': [{'task': '4.3.3'}]}), encoding='utf-8')

    def add_validated_core_closure(self, context: ValidationContext) -> None:
        """Add the successful roadmap result required for an eligible release."""
        self.write_core_completion(context)
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

    def test_registry_list_publish_flag_fails(self):
        """Reject registry allow-lists while the D05 publication gate stands."""
        for registries in (['crates-io'], ['private-registry']):
            with self.subTest(registries=registries):
                package = MANIFEST['package'] | {'publish': registries}
                with self.assertRaisesRegex(AssertionError, 'publish = false'):
                    check_manifest({'package': package})

    def test_other_licence_fails(self):
        """Reject a package licence that disagrees with accepted D04."""
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
