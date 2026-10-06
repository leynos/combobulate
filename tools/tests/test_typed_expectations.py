"""Reject expected values that Python equality silently coerces across JSON types."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext, same_typed_value
from docs_validation.costs import check_cost_examples
from docs_validation.semantics import check_examples

ROOT = Path(__file__).resolve().parents[2]


class TypedExpectations(unittest.TestCase):
    """Distinguish domain-valid arithmetic results from malformed expected witnesses."""

    def test_scalar_values_require_the_same_concrete_json_type(self):
        for actual, expected in ((0, False), (1, True), (1, 1.0), (False, 0), (0.0, 0)):
            with self.subTest(actual=actual, expected=expected):
                self.assertFalse(same_typed_value(actual, expected))
        for value in (0, 1, False, True, 1.0, None, 'overflow'):
            with self.subTest(value=value):
                self.assertTrue(same_typed_value(value, value))

    def test_nested_values_reject_coercion_and_preserve_container_contracts(self):
        cases = (
            ([0, [1]], [False, [1]]),
            ([0, [1]], [0, [1.0]]),
            ({'shape': [1]}, {'shape': [True]}),
            ({'shape': [1]}, {'shape': [1.0]}),
            ([1], (1,)),
            ([1], [1, 1]),
            ({'x': 1}, {'y': 1}),
        )
        for actual, expected in cases:
            with self.subTest(actual=actual, expected=expected):
                self.assertFalse(same_typed_value(actual, expected))
        value = {'shape': [0, [1]], 'valid': False, 'result': None, 'status': 'overflow'}
        self.assertTrue(same_typed_value(value, copy.deepcopy(value)))
        self.assertTrue(same_typed_value({'x': 1, 'y': 2}, {'y': 2, 'x': 1}))

    def test_full_semantic_ledger_rejects_scalar_and_nested_wrong_types(self):
        ledger = ValidationContext(ROOT).load('spec/examples.json')
        mutations = (('EX13', False), ('EX01', 9.0), ('EX03', [10, 7, 9.0]))
        for case_id, expected in mutations:
            mutated = copy.deepcopy(ledger)
            next(case for case in mutated['cases'] if case['id'] == case_id)['expected'] = expected
            context = ValidationContext(ROOT)
            with self.subTest(case_id=case_id), patch.object(context, 'load', return_value=mutated):
                with self.assertRaisesRegex(AssertionError, 'Wrong result in ' + case_id):
                    check_examples(context)
        context = ValidationContext(ROOT)
        check_examples(context)
        self.assertEqual(context.results[-1]['status'], 'pass')

    def test_full_cost_ledger_rejects_boolean_and_floating_expected_counts(self):
        ledger = ValidationContext(ROOT).load('spec/cost-cases.json')
        mutations = (('K07', True), ('K06', 0.0), ('K10', 8386560.0))
        for case_id, expected in mutations:
            mutated = copy.deepcopy(ledger)
            next(case for case in mutated['cases'] if case['id'] == case_id)['expected'] = expected
            context = ValidationContext(ROOT)
            with self.subTest(case_id=case_id), patch.object(context, 'load', return_value=mutated):
                with self.assertRaisesRegex(AssertionError, 'Wrong cost result ' + case_id):
                    check_cost_examples(context)
        context = ValidationContext(ROOT)
        check_cost_examples(context)
        self.assertEqual(context.results[-1]['status'], 'pass')


    def test_semantic_ledger_requires_an_explicit_single_outcome(self):
        ledger = ValidationContext(ROOT).load('spec/examples.json')
        mutations = (
            ('EX11', 'expected', None, True),
            ('EX03', 'expected_shape', [10, 7, 9], False),
            ('EX03', 'expected_shape', [1], False),
            ('EX20', 'expected', None, False),
        )
        for case_id, field, value, remove in mutations:
            mutated = copy.deepcopy(ledger)
            case = next(case for case in mutated['cases'] if case['id'] == case_id)
            if remove:
                case.pop(field)
            else:
                case[field] = value
            context = ValidationContext(ROOT)
            with self.subTest(case_id=case_id, field=field, remove=remove):
                with patch.object(context, 'load', return_value=mutated):
                    with self.assertRaisesRegex(AssertionError, 'Expected exactly one outcome field'):
                        check_examples(context)
        context = ValidationContext(ROOT)
        check_examples(context)
        self.assertEqual(context.results[-1]['status'], 'pass')

    def test_expected_errors_must_match_actual_semantic_failures(self):
        ledger = ValidationContext(ROOT).load('spec/examples.json')
        for case_id, replacement in (('EX07', 'Contraction'), ('EX11', 'EmptyMean')):
            mutated = copy.deepcopy(ledger)
            case = next(case for case in mutated['cases'] if case['id'] == case_id)
            case.pop('expected', None)
            case['expected_error'] = replacement
            context = ValidationContext(ROOT)
            with self.subTest(case_id=case_id), patch.object(context, 'load', return_value=mutated):
                with self.assertRaisesRegex(AssertionError, '(Wrong failure|Missing error)'):
                    check_examples(context)


if __name__ == '__main__':
    unittest.main()
