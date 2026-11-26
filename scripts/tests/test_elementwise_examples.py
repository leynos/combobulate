"""Check the SC-12 elementwise-addition examples and their seeded mutation."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.contract_examples import expected_outcome, outcome
from docs_validation.elementwise_examples import (
    I64_MAX, I64_MIN, add_vectors, checked_add, elementwise_add, wrapping_add,
)
from docs_validation.semantics import SemanticFailure

ROOT = Path(__file__).resolve().parents[2]
MUTANT = frozenset({'wrapping-add'})


def cases() -> dict[str, dict]:
    """Load the recorded contract cases by identifier; e.g. ``cases()['EX89']``."""
    document = json.loads((ROOT / 'spec/examples.json').read_text(encoding='utf-8'))
    return {case['id']: case for case in document['contract_cases']}


class ElementwiseAddExamples(unittest.TestCase):
    """Check SC-12's recorded examples against the documented model."""

    def test_success_and_empty_vectors_agree_with_the_examples(self):
        """Add pointwise and accept the empty vector as the empty result."""
        self.assertEqual(add_vectors([1, 2, 3], [10, 20, 30], frozenset()), [11, 22, 33])
        self.assertEqual(add_vectors([], [], frozenset()), [])

    def test_both_i64_boundaries_are_successes(self):
        """Reject treating a boundary sum as an overflow."""
        self.assertEqual(checked_add(I64_MAX, 0), I64_MAX)
        self.assertEqual(checked_add(I64_MIN, 0), I64_MIN)
        self.assertEqual(checked_add(I64_MAX, -1), I64_MAX - 1)

    def test_overflow_is_reported_at_the_least_overflowing_position(self):
        """Name the least overflowing position, not the first one examined after it."""
        with self.assertRaisesRegex(SemanticFailure, 'IntegerOverflow at position 1'):
            add_vectors([0, I64_MAX], [0, 1], frozenset())
        with self.assertRaisesRegex(SemanticFailure, 'IntegerOverflow at position 0'):
            add_vectors([I64_MAX, I64_MAX], [1, 1], frozenset())

    def test_mismatched_lengths_fail_as_shape_agreement(self):
        """Fail shape agreement before examining any element."""
        for left, right in (([1, 2, 3], [1, 2]), ([], [1]), ([1], [])):
            with self.subTest(lengths=(len(left), len(right))), \
                    self.assertRaisesRegex(SemanticFailure, '^ShapeAgreement$'):
                elementwise_add({'id': 'inline', 'args': [left, right]}, frozenset())

    def test_wrapping_add_is_the_recorded_mutant_arithmetic(self):
        """Wrap modulo 2**64 instead of failing, so the mutation is observable."""
        self.assertEqual(wrapping_add(I64_MAX, 1), I64_MIN)
        self.assertEqual(wrapping_add(I64_MIN, -1), I64_MAX)
        self.assertEqual(wrapping_add(2, 3), 5)


class ElementwiseAddRecordedExamples(unittest.TestCase):
    """Require every recorded SC-12 case to match the model, with and without the mutation."""

    def test_every_sc12_example_matches_its_expectation(self):
        """Evaluate EX89 onward through the shared dispatcher."""
        selected = {identifier: case for identifier, case in cases().items()
                    if case.get('contract') == 'SC-12'}
        self.assertEqual(sorted(selected), ['EX89', 'EX90', 'EX91', 'EX92', 'EX93', 'EX94', 'EX95'],
                         'SC-12 owns exactly the recorded elementwise examples')
        for identifier, case in selected.items():
            with self.subTest(case=identifier):
                self.assertEqual(outcome(case), expected_outcome(case),
                                 'the documentation model must reproduce the typed example')

    def test_the_seeded_mutation_changes_only_the_overflow_outcomes(self):
        """Keep wrapping-add discriminating rather than a change nobody can observe."""
        changed = {identifier for identifier, case in cases().items()
                   if case.get('contract') == 'SC-12' and outcome(case, MUTANT) != outcome(case)}
        self.assertEqual(changed, {'EX92', 'EX93'},
                         'wrapping-add must change both overflow examples and nothing else')


if __name__ == '__main__':
    unittest.main()
