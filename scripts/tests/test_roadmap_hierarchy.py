"""Keep emitted GIST task order consistent with prerequisites and numbered hierarchy."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_docs import LEDGER_DEPENDENCIES
from docs_validation.context import ValidationContext
from docs_validation.ledger import (
    check_catalogue_and_roadmap, check_dependencies, collect_tasks,
)

ROOT = Path(__file__).resolve().parents[2]


class RoadmapHierarchy(unittest.TestCase):
    """Exercise hierarchy integrity before generated Markdown can legitimize bad ledgers."""

    def test_dependencies_follow_emitted_order_and_declare_lists_of_string_ids(self):
        """Require typed dependency lists and place each prerequisite before its consumer."""
        tasks = {'1.1.2': {'requires': ['1.1.1']}, '1.1.1': {'requires': []}}
        with self.assertRaisesRegex(AssertionError, 'emitted task order'):
            check_dependencies(tasks)
        for invalid in ('', {}, '1.1.1', [True], [1], [None]):
            with self.subTest(requires=invalid), self.assertRaisesRegex(AssertionError, 'Malformed dependencies'):
                check_dependencies({'1.1.1': {'requires': invalid}})
        with self.assertRaises(KeyError):
            check_dependencies({'1.1.1': {}})
        check_dependencies({'1.1.1': {'requires': []}, '1.1.2': {'requires': ['1.1.1']}})
        check_dependencies({'1.1.2': {'requires': []}, '1.1.1': {'requires': []}})

    def test_full_ledger_rejects_prerequisite_reordered_after_its_consumer(self):
        """Reject a complete roadmap whose same-step prerequisite follows its consumer."""
        phases = ValidationContext(ROOT).load('spec/roadmap.json')['phases']
        for phase in phases:
            for step in phase['steps']:
                ids = {task['id']: index for index, task in enumerate(step['tasks'])}
                for consumer in step['tasks']:
                    matching = next((dependency for dependency in consumer['requires'] if dependency in ids), None)
                    if matching is not None:
                        prerequisite = step['tasks'].pop(ids[matching])
                        consumer_position = next(index for index, task in enumerate(step['tasks'])
                                                 if task['id'] == consumer['id'])
                        step['tasks'].insert(consumer_position + 1, prerequisite)
                        tasks, _ = collect_tasks(phases)
                        with self.assertRaisesRegex(AssertionError, 'emitted task order'):
                            check_dependencies(tasks)
                        return
        self.fail('Expected a real same-step dependency in the complete roadmap ledger')

    def test_phase_numbers_are_positive_unique_ascending_integers(self):
        """Reject malformed, repeated, or descending phase numbers in the roadmap."""
        original = ValidationContext(ROOT).load('spec/roadmap.json')['phases']
        for invalid in (True, 1.0, '1', 0, -1):
            mutated = copy.deepcopy(original)
            mutated[0]['number'] = invalid
            with self.subTest(number=invalid), self.assertRaisesRegex(AssertionError, 'Malformed phase number'):
                collect_tasks(mutated)
        duplicate = copy.deepcopy(original)
        duplicate[0]['number'] = duplicate[1]['number']
        reverse = copy.deepcopy(original)
        reverse[0], reverse[1] = reverse[1], reverse[0]
        for mutated in (duplicate, reverse):
            with self.subTest(numbers=[phase['number'] for phase in mutated]):
                with self.assertRaisesRegex(AssertionError, 'Phase numbers must be unique and ascending'):
                    collect_tasks(mutated)

    def test_step_identity_matches_parent_and_is_canonical_unique_and_ascending(self):
        """Require canonical step identities under their parent phase in ascending order."""
        original = ValidationContext(ROOT).load('spec/roadmap.json')['phases']
        for invalid in ('2.1', '1.0', '1.01', '1.1.1', True):
            mutated = copy.deepcopy(original)
            mutated[0]['steps'][0]['number'] = invalid
            with self.subTest(step=invalid), self.assertRaisesRegex(AssertionError, '(Misnumbered step|Malformed step)'):
                collect_tasks(mutated)
        duplicate = copy.deepcopy(original)
        duplicate[0]['steps'].insert(1, copy.deepcopy(duplicate[0]['steps'][0]))
        reverse = copy.deepcopy(original)
        reverse[0]['steps'].reverse()
        for mutated in (duplicate, reverse):
            with self.assertRaisesRegex(AssertionError, 'Step numbers must be unique and ascending'):
                collect_tasks(mutated)

    def test_tasks_have_canonical_identities_in_their_containing_step(self):
        """Require unique canonical task IDs that match their containing step."""
        original = ValidationContext(ROOT).load('spec/roadmap.json')['phases']
        for invalid in ('2.1.1', '1.2.1', '1.1.0', '1.1.01', '1.1.1.1', True):
            mutated = copy.deepcopy(original)
            mutated[0]['steps'][0]['tasks'][0]['id'] = invalid
            with self.subTest(task=invalid), self.assertRaisesRegex(AssertionError, '(Misnumbered task|Malformed task)'):
                collect_tasks(mutated)
        mutated = copy.deepcopy(original)
        tasks = mutated[0]['steps'][0]['tasks']
        tasks.append(copy.deepcopy(tasks[0]))
        with self.assertRaisesRegex(AssertionError, 'Duplicate task'):
            collect_tasks(mutated)

    def test_complete_ledger_hierarchy_rejection_precedes_generator_drift_checks(self):
        """Reject malformed hierarchy before drift checks without changing loaded modules."""
        original = ValidationContext(ROOT).load('spec/roadmap.json')
        mutated = copy.deepcopy(original)
        mutated['phases'][0]['number'] = 2
        context = ValidationContext(ROOT)
        original_load = context.load
        with patch.object(context, 'load', side_effect=lambda name:
                          mutated if name == 'spec/roadmap.json' else original_load(name)):
            with self.assertRaisesRegex(AssertionError, 'Phase numbers must be unique and ascending'):
                check_catalogue_and_roadmap(context, LEDGER_DEPENDENCIES)
        context = ValidationContext(ROOT)
        before = sys.modules.copy()
        check_catalogue_and_roadmap(context, LEDGER_DEPENDENCIES)
        self.assertTrue(all(row['status'] == 'pass' for row in context.results))
        self.assertEqual(set(sys.modules), set(before), 'the ledger check must not add process-global modules')
        self.assertTrue(all(sys.modules[name] is module for name, module in before.items()),
                        'the ledger check must not replace process-global modules')


if __name__ == '__main__':
    unittest.main()
