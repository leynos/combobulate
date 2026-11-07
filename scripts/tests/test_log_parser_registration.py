"""Require parser registration to be earned by the corpus behind it (VO-13).

VO-13 makes `registered_log_parsers` a claim rather than a list. Each name
must have a committed corpus whose *parsed* decisions reach the classes the
gate's rules key on, and the registry must be enforced by a design check that
runs in `make design-check`.

The non-vacuity case is the one that matters: a registry entry whose corpus
cannot reach one class must fail. Without it the check would pass for any
corpus at all, including one that decides nothing but success.

Examples
--------
>>> sorted(required_classes({'verified'}))
['counterexample', 'resource-exhausted', 'skipped', 'some-unsatisfied-witness', 'tool-error', 'unsupported-or-solver-unknown']
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.log_parser_registration import (
    CORPUS, REGISTRY, check_log_parser_registration, required_classes,
)

ROOT = Path(__file__).resolve().parents[2]
COMPLETE = {'verified', 'counterexample', 'resource-exhausted', 'skipped', 'tool-error', 'unsupported'}
WITNESSES = {'satisfied', 'unsatisfied'}


class RequiredClasses(unittest.TestCase):
    """The class list VO-13 requires is exactly the one the gate's rules key on."""

    def test_a_complete_corpus_leaves_nothing_missing(self):
        """Require every class to be reported covered by a corpus that reaches it."""
        self.assertEqual(required_classes(COMPLETE, WITNESSES), set(),
                         'a corpus reaching every named class must leave nothing missing')

    def test_a_solver_unknown_corpus_also_covers_the_undetermined_class(self):
        """Require either undetermined outcome to satisfy the disjunction."""
        outcomes = (COMPLETE - {'unsupported'}) | {'solver-unknown'}
        self.assertEqual(required_classes(outcomes, WITNESSES), set(),
                         'solver-unknown must stand in for unsupported')

    def test_a_missing_timeout_is_reported(self):
        """Require the resource-exhausted class to be named when a corpus lacks it."""
        self.assertEqual(required_classes(COMPLETE - {'resource-exhausted'}, WITNESSES),
                         {'resource-exhausted'}, 'a corpus without a timeout must be refused')

    def test_a_corpus_whose_covers_all_succeed_cannot_vouch_for_the_witness_class(self):
        """Require the unsatisfied-witness class to be its own axis.

        An unsatisfied cover is not an outcome: ``unsatisfied_cover`` decides
        ``verified`` while its cover failed, so a check reading outcomes alone
        would let that log be deleted without noticing.
        """
        self.assertEqual(required_classes(COMPLETE, {'satisfied'}), {'some-unsatisfied-witness'},
                         'a corpus without an unsatisfied cover must be refused')

    def test_a_corpus_of_only_successes_is_refused(self):
        """Require a vacuous corpus to be refused for every class it lacks."""
        self.assertEqual(required_classes({'verified'}),
                         {'counterexample', 'resource-exhausted', 'skipped', 'some-unsatisfied-witness',
                          'tool-error', 'unsupported-or-solver-unknown'},
                         'a success-only corpus must not satisfy registration')


class RegistrationCheck(unittest.TestCase):
    """The checker reads the real registry and the real corpus."""

    def test_the_repository_registers_kani_and_its_corpus_covers_every_class(self):
        """Require the committed registry and corpus to satisfy VO-13 as they stand."""
        context = ValidationContext(ROOT)
        check_log_parser_registration(context)
        self.assertIn('kani', context.load(REGISTRY)['registered_log_parsers'],
                      'the Kani adapter is integrated, so the registry must name it')
        result = next(row for row in context.results if row['check'] == 'log-parser-registration')
        self.assertEqual(result['status'], 'pass', 'the committed corpus must cover every class')

    def test_a_registry_entry_without_a_corpus_is_refused(self):
        """Require an unreadable registration to fail rather than pass silently."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_minimum(root, ['verus'])
            with self.assertRaisesRegex(AssertionError, 'no committed corpus'):
                check_log_parser_registration(ValidationContext(root))

    def test_a_registry_entry_whose_corpus_lacks_the_timeout_class_is_refused(self):
        """Require the non-vacuity case VO-13 names: the missing timeout must fail."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_minimum(root, ['kani'])
            expected = root / CORPUS / 'expected.json'
            document = json.loads(expected.read_text(encoding='utf-8'))
            for entry in document['decisions'].values():
                if entry['outcome'] == 'resource-exhausted':
                    entry['outcome'] = 'verified'
            expected.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
            with self.assertRaisesRegex(AssertionError, 'resource-exhausted'):
                check_log_parser_registration(ValidationContext(root))

    def test_a_corpus_without_an_unsatisfied_cover_is_refused(self):
        """Require the witness axis to be read, not just the outcomes.

        Every outcome stays present here, so a check that read only outcomes
        would still pass. The log this removes decides ``verified`` while its
        cover failed, which is what makes the class visible at all.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_minimum(root, ['kani'])
            expected = root / CORPUS / 'expected.json'
            document = json.loads(expected.read_text(encoding='utf-8'))
            for entry in document['decisions'].values():
                entry['witnesses'] = ['satisfied']
            expected.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
            with self.assertRaisesRegex(AssertionError, 'some-unsatisfied-witness'):
                check_log_parser_registration(ValidationContext(root))

    def test_a_corpus_that_decides_nothing_is_refused(self):
        """Require an empty decision record to fail rather than vacuously pass."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_minimum(root, ['kani'])
            (root / CORPUS / 'expected.json').write_text(
                json.dumps({'decisions': {}}), encoding='utf-8')
            with self.assertRaisesRegex(AssertionError, 'decides nothing'):
                check_log_parser_registration(ValidationContext(root))

    @staticmethod
    def _copy_minimum(root: Path, parsers: list[str]) -> None:
        """Write the registry and a copy of the corpus into a scratch root."""
        (root / 'spec').mkdir(parents=True)
        (root / REGISTRY).write_text(
            json.dumps({'registered_log_parsers': parsers}), encoding='utf-8')
        (root / CORPUS).mkdir(parents=True)
        (root / CORPUS / 'expected.json').write_bytes((ROOT / CORPUS / 'expected.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
