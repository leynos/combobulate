"""Reject iterable JSON containers that do not satisfy the cost model's list contracts."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.costs import check_cost_examples, shape_product, tracked_peak

ROOT = Path(__file__).resolve().parents[2]


class CostContainers(unittest.TestCase):
    """Keep scalar shapes and scratch-only stages valid without accepting strings or objects."""

    def test_full_ledger_rejects_empty_string_and_object_shapes(self):
        ledger = ValidationContext(ROOT).load('spec/cost-cases.json')
        for invalid in ('', {}):
            mutated = copy.deepcopy(ledger)
            next(case for case in mutated['cases'] if case['id'] == 'K07')['shape'] = invalid
            context = ValidationContext(ROOT)
            with self.subTest(shape=invalid), patch.object(context, 'load', return_value=mutated):
                with self.assertRaisesRegex(AssertionError, 'Malformed cost shape'):
                    check_cost_examples(context)

    def test_full_ledger_rejects_string_and_object_live_allocations(self):
        ledger = ValidationContext(ROOT).load('spec/cost-cases.json')
        updates = (
            {'capacities': {'a': 80, 'b': 40},
             'stages': [{'live': ['a', 'a'], 'scratch': 8}, {'live': 'ab', 'scratch': 16}]},
            {'stages': [{'live': ['source', 'source'], 'scratch': 8},
                        {'live': {'source': None, 'output': None}, 'scratch': 16}]},
        )
        for update in updates:
            mutated = copy.deepcopy(ledger)
            next(case for case in mutated['cases'] if case['id'] == 'K12').update(update)
            context = ValidationContext(ROOT)
            with self.subTest(update=update), patch.object(context, 'load', return_value=mutated):
                with self.assertRaisesRegex(AssertionError, 'Malformed live allocations'):
                    check_cost_examples(context)

    def test_dimension_list_and_live_id_element_boundaries(self):
        for invalid in ('', {}, None, False):
            with self.subTest(shape=invalid), self.assertRaisesRegex(AssertionError, 'Malformed cost shape'):
                shape_product({'shape': invalid, 'target_bits': 64})
        for invalid in (True, 1, 1.0, None, ['source']):
            case = {'capacities': {'source': 80},
                    'stages': [{'live': [invalid], 'scratch': 8}]}
            with self.subTest(allocation_id=invalid):
                with self.assertRaisesRegex(AssertionError, 'Malformed live allocation ID'):
                    tracked_peak(case)
        for invalid in ('', {}):
            with self.subTest(stages=invalid), self.assertRaisesRegex(AssertionError, 'Malformed stages'):
                tracked_peak({'capacities': {}, 'stages': invalid})

    def test_valid_scalar_zero_shapes_empty_stages_and_aliases_preserve_results(self):
        self.assertEqual(shape_product({'shape': [], 'target_bits': 64}), 1)
        self.assertEqual(shape_product({'shape': [0, 2**64], 'target_bits': 64}), 0)
        for live, scratch, expected in (([], 0, 0), ([], 8, 8), (['source', 'source'], 8, 88)):
            with self.subTest(live=live, scratch=scratch):
                self.assertEqual(tracked_peak({'capacities': {'source': 80},
                                 'stages': [{'live': live, 'scratch': scratch}]}), expected)
        ledger = ValidationContext(ROOT).load('spec/cost-cases.json')
        next(case for case in ledger['cases'] if case['id'] == 'K12')['stages'].append(
            {'live': [], 'scratch': 136})
        context = ValidationContext(ROOT)
        with patch.object(context, 'load', return_value=ledger):
            check_cost_examples(context)
        self.assertEqual(context.results[-1]['status'], 'pass')


if __name__ == '__main__':
    unittest.main()
