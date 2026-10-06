"""Keep malformed semantic examples distinct from valid scalar and empty cases."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.semantics import SemanticFailure, agreement, checked_add, evaluate


class SemanticDomains(unittest.TestCase):
    """Check each shape/policy boundary before Python can coerce malformed inputs."""

    def test_subtraction_models_require_the_declared_operation(self):
        for kind in ('reduce', 'fold_left', 'scan', 'scan_left'):
            for operation in ('suub', 'add', None, True):
                with self.subTest(kind=kind, operation=operation):
                    with self.assertRaisesRegex(AssertionError, 'Unknown subtraction operation'):
                        evaluate({'kind': kind, 'operation': operation, 'input': [10, 3, 2]})
        for kind in ('reduce', 'fold_left'):
            with self.subTest(kind=kind), self.assertRaisesRegex(SemanticFailure, 'EmptyReduction'):
                evaluate({'kind': kind, 'operation': 'sub', 'input': []})
        for kind in ('scan', 'scan_left'):
            with self.subTest(kind=kind):
                self.assertEqual(evaluate({'kind': kind, 'operation': 'sub', 'input': []}), [])

    def test_policy_flags_require_booleans_even_on_shortcuts(self):
        for invalid in ('false', 'true', 0, 1, None):
            with self.subTest(value=invalid):
                with self.assertRaisesRegex(AssertionError, 'Malformed broadcast policy'):
                    agreement([], [], invalid)
                with self.assertRaisesRegex(AssertionError, 'Malformed null policy'):
                    evaluate({'kind': 'sum', 'input': [], 'skip_nulls': invalid})
        self.assertEqual(agreement([], [0], False), [0])
        self.assertEqual(evaluate({'kind': 'sum', 'input': [1, None, 3], 'skip_nulls': True}), 4)
        self.assertIsNone(evaluate({'kind': 'sum', 'input': [1, None, 3], 'skip_nulls': False}))
        self.assertEqual(evaluate({'kind': 'sum', 'input': [], 'skip_nulls': False}), 0)

    def test_every_shape_operand_rejects_invalid_dimensions(self):
        operands = (
            ({'kind': 'rank_transpose_shape', 'input_shape': [2, 3], 'cell_rank': 1}, 'input_shape'),
            ({'kind': 'rows_mean_shape', 'input_shape': [2, 3]}, 'input_shape'),
            ({'kind': 'agreement', 'left': [2, 3], 'right': [2, 3], 'broadcast': False}, 'left'),
            ({'kind': 'agreement', 'left': [2, 3], 'right': [2, 3], 'broadcast': False}, 'right'),
            ({'kind': 'inner_shape', 'left': [2, 3], 'right': [3, 4]}, 'left'),
            ({'kind': 'inner_shape', 'left': [2, 3], 'right': [3, 4]}, 'right'),
            ({'kind': 'reshape', 'input_shape': [2, 3], 'target_shape': [3, 2]}, 'input_shape'),
            ({'kind': 'reshape', 'input_shape': [2, 3], 'target_shape': [3, 2]}, 'target_shape'),
        )
        for template, operand in operands:
            for invalid in ([-2, -3], [True], [2.0], '23', None):
                case = copy.deepcopy(template)
                case[operand] = invalid
                with self.subTest(kind=case['kind'], operand=operand, invalid=invalid):
                    with self.assertRaisesRegex(AssertionError, 'Malformed shape'):
                        evaluate(case)

    def test_scalar_and_zero_shapes_remain_valid(self):
        cases = (
            ({'kind': 'rank_transpose_shape', 'input_shape': [], 'cell_rank': 0}, []),
            ({'kind': 'rank_transpose_shape', 'input_shape': [0, 3, 4], 'cell_rank': 2}, [0, 4, 3]),
            ({'kind': 'rows_mean_shape', 'input_shape': [0, 0]}, [0]),
            ({'kind': 'agreement', 'left': [], 'right': [], 'broadcast': False}, []),
            ({'kind': 'reshape', 'input_shape': [], 'target_shape': [1]}, [1]),
            ({'kind': 'reshape', 'input_shape': [0, 3], 'target_shape': [0]}, [0]),
            ({'kind': 'inner_shape', 'left': [0, 3], 'right': [3, 0]}, [0, 0]),
        )
        for case, expected in cases:
            with self.subTest(kind=case['kind']):
                self.assertEqual(evaluate(case), expected)
        with self.assertRaisesRegex(SemanticFailure, 'EmptyMean'):
            evaluate({'kind': 'rows_mean_shape', 'input_shape': [3, 0]})

    def test_axis_consuming_operations_reject_scalar_inputs(self):
        cases = (
            {'kind': 'rows_mean_shape', 'input_shape': []},
            {'kind': 'inner_shape', 'left': [], 'right': [3]},
            {'kind': 'inner_shape', 'left': [3], 'right': []},
        )
        for case in cases:
            with self.subTest(kind=case['kind']), self.assertRaisesRegex(AssertionError, 'expected at least one axis'):
                evaluate(case)

    def test_stencil_rejects_ragged_boards_and_accepts_empty_frames(self):
        for board in ([[1, 0, 0], [0, 0, 1, 0]], [[1], []], [1], None):
            with self.subTest(board=board), self.assertRaisesRegex(AssertionError, 'Malformed board'):
                evaluate({'kind': 'neighbour_sum', 'input': board})
        for board, expected in (([], []), ([[], []], [[], []]), ([[1]], [[0]])):
            with self.subTest(board=board):
                self.assertEqual(evaluate({'kind': 'neighbour_sum', 'input': board}), expected)

    def test_checked_add_rejects_invalid_operands_before_cancellation(self):
        for invalid in (True, 1.0, -2**63 - 1, 2**63):
            for left, right in ((invalid, -1), (-1, invalid)):
                with self.subTest(left=left, right=right):
                    with self.assertRaisesRegex(AssertionError, 'Malformed I64 operand'):
                        checked_add(left, right)
            with self.subTest(singleton=invalid), self.assertRaisesRegex(AssertionError, 'Malformed I64 operand'):
                evaluate({'kind': 'checked_add_grouping', 'input': [invalid], 'association': 'left'})
        self.assertEqual(checked_add(-2**63, 0), -2**63)
        self.assertEqual(checked_add(2**63 - 1, 0), 2**63 - 1)
        with self.assertRaisesRegex(SemanticFailure, 'IntegerOverflow'):
            checked_add(2**63 - 1, 1)
        with self.assertRaisesRegex(SemanticFailure, 'EmptyReduction'):
            evaluate({'kind': 'checked_add_grouping', 'input': [], 'association': 'right'})

    def test_integer_models_reject_coercion_even_before_null_propagation(self):
        for invalid in (True, 1.0, '1'):
            cases = (
                {'kind': 'reduce', 'operation': 'sub', 'input': [invalid]},
                {'kind': 'scan', 'operation': 'sub', 'input': [invalid]},
                {'kind': 'sum', 'input': [None, invalid], 'skip_nulls': False},
                {'kind': 'neighbour_sum', 'input': [[invalid]]},
            )
            for case in cases:
                with self.subTest(kind=case['kind'], invalid=invalid):
                    with self.assertRaisesRegex(AssertionError, 'Malformed integer operand'):
                        evaluate(case)
        self.assertEqual(evaluate({'kind': 'reduce', 'operation': 'sub', 'input': [10, 3, 2]}), 9)
        self.assertEqual(evaluate({'kind': 'sum', 'input': [None, 1], 'skip_nulls': True}), 1)


if __name__ == '__main__':
    unittest.main()
