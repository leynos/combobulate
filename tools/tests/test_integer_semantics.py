"""Distinguish checked I64 execution from Python's unbounded integer arithmetic."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.costs import classify_admission
from docs_validation.semantics import SemanticFailure, evaluate

I64_MIN = -(2**63)
I64_MAX = 2**63 - 1


class CheckedIntegerModels(unittest.TestCase):
    """Check association, overflow, null policy, and stencil order against the design."""

    def test_subtraction_reductions_and_scans_report_i64_overflow(self):
        for kind in ('reduce', 'fold_left', 'scan', 'scan_left'):
            for values in ([I64_MIN, 1], [I64_MAX, -1]):
                with self.subTest(kind=kind, values=values):
                    with self.assertRaisesRegex(SemanticFailure, 'IntegerOverflow'):
                        evaluate({'kind': kind, 'operation': 'sub', 'input': values})

    def test_right_subtraction_rejects_overflow_hidden_by_final_cancellation(self):
        values = [I64_MIN, I64_MIN, 1]
        for kind in ('reduce', 'scan'):
            with self.subTest(kind=kind), self.assertRaisesRegex(SemanticFailure, 'IntegerOverflow'):
                evaluate({'kind': kind, 'operation': 'sub', 'input': values})
        self.assertEqual(evaluate({'kind': 'fold_left', 'operation': 'sub', 'input': values}), -1)
        self.assertEqual(evaluate({'kind': 'scan_left', 'operation': 'sub', 'input': values}),
                         [I64_MIN, 0, -1])

    def test_sum_uses_exact_right_association_and_checked_addition(self):
        with self.assertRaisesRegex(SemanticFailure, 'IntegerOverflow'):
            evaluate({'kind': 'sum', 'input': [-1, I64_MAX, 1], 'skip_nulls': False})
        self.assertEqual(evaluate({'kind': 'sum', 'input': [I64_MAX, 1, -1], 'skip_nulls': False}),
                         I64_MAX)
        for values, expected in (([], 0), ([I64_MIN], I64_MIN), ([I64_MAX], I64_MAX)):
            with self.subTest(values=values):
                self.assertEqual(evaluate({'kind': 'sum', 'input': values, 'skip_nulls': False}), expected)

    def test_null_policy_precedes_arithmetic_without_reordering_valid_values(self):
        values = [None, -1, I64_MAX, 1]
        self.assertIsNone(evaluate({'kind': 'sum', 'input': values, 'skip_nulls': False}))
        with self.assertRaisesRegex(SemanticFailure, 'IntegerOverflow'):
            evaluate({'kind': 'sum', 'input': values, 'skip_nulls': True})
        self.assertEqual(evaluate({'kind': 'sum', 'input': [None, None], 'skip_nulls': True}), 0)
        self.assertIsNone(evaluate({'kind': 'sum', 'input': [None, None], 'skip_nulls': False}))

    def test_stencil_sums_preserve_order_and_overflow_checks(self):
        with self.assertRaisesRegex(SemanticFailure, 'IntegerOverflow'):
            evaluate({'kind': 'neighbour_sum', 'input': [[0, -1], [I64_MAX, 1]]})
        self.assertEqual(evaluate({'kind': 'neighbour_sum', 'input': [[0, I64_MAX], [0, 0]]}),
                         [[I64_MAX, 0], [I64_MAX, I64_MAX]])
        self.assertEqual(evaluate({'kind': 'neighbour_sum', 'input': [[I64_MIN]]}), [[0]])

    def test_all_integer_models_reject_out_of_range_singletons(self):
        for invalid in (I64_MIN - 1, I64_MAX + 1):
            cases = (
                {'kind': 'reduce', 'operation': 'sub', 'input': [invalid]},
                {'kind': 'fold_left', 'operation': 'sub', 'input': [invalid]},
                {'kind': 'scan', 'operation': 'sub', 'input': [invalid]},
                {'kind': 'scan_left', 'operation': 'sub', 'input': [invalid]},
                {'kind': 'sum', 'input': [None, invalid], 'skip_nulls': False},
                {'kind': 'neighbour_sum', 'input': [[invalid]]},
            )
            for case in cases:
                with self.subTest(kind=case['kind'], invalid=invalid):
                    with self.assertRaisesRegex(AssertionError, 'Malformed I64 operand'):
                        evaluate(case)

    def test_optional_cost_intervals_reject_malformed_present_bounds(self):
        invalid_pairs = ((True, 5), (0, 5.0), ('0', '5'), (-1, 5), (5, 4),
                         (None, 5), (0, None))
        for classification in ('estimate', 'unknown'):
            for lower, upper in invalid_pairs:
                with self.subTest(classification=classification, lower=lower, upper=upper):
                    with self.assertRaisesRegex(AssertionError, 'Malformed cost interval'):
                        classify_admission({'classification': classification, 'lower': lower,
                                            'upper': upper, 'budget': 10})
            for lower, upper in ((None, None), (0, 0), (0, 10)):
                with self.subTest(classification=classification, lower=lower, upper=upper):
                    self.assertEqual(classify_admission({'classification': classification,
                                     'lower': lower, 'upper': upper, 'budget': 10}),
                                     'runtime-obligation-or-strict-refusal')


if __name__ == '__main__':
    unittest.main()
