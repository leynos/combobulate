"""Exercise documentation validation boundaries and non-vacuous controls."""
from __future__ import annotations

import operator
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.costs import (
    classify_admission, right_prefix_work, shape_product, tracked_peak,
)
from docs_validation.ledger import check_dependencies, collect_tasks
from docs_validation.markdown import (
    check_local_link, check_markdown, generated_matches, headings, semantic_tokens,
)
from docs_validation.semantics import (
    SemanticFailure, agreement, checked_add, evaluate, left_reduce, right_reduce,
)


class MarkdownBoundaries(unittest.TestCase):
    """Check explicit inputs, local-link confinement, and generated-content drift."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.context = ValidationContext(self.root)
        for path in self.context.markdown_paths():
            path.parent.mkdir(exist_ok=True)
            path.write_text('# Title\n', encoding='utf-8')

    def test_excludes_inherited_guides_and_build_outputs(self):
        for relative in ('docs/developers-guide.md', 'target/generated.md', '.git/notes.md'):
            path = self.root / relative
            path.parent.mkdir(exist_ok=True)
            path.write_text('Malformed markdown with no title')
        check_markdown(self.context)
        self.assertEqual(self.context.results[0]['count'], 10)

    def test_json_inputs_exclude_repository_and_build_metadata(self):
        (self.root / 'spec').mkdir()
        (self.root / 'spec/cases.json').write_text('{}')
        (self.root / 'target').mkdir()
        (self.root / 'target/bad.json').write_text('broken')
        (self.root / 'package.json').write_text('broken')
        paths = [str(path.relative_to(self.root)) for path in self.context.json_paths()]
        self.assertEqual(paths, ['spec/cases.json', 'docs/revision-comparison.json',
                                 'docs/validation-results.json'])

    def test_rejects_broken_anchor_and_parent_escape(self):
        for href, message in (('#missing', 'Broken anchor'), ('../outside.md', 'Out-of-pack')):
            with self.subTest(href=href), self.assertRaisesRegex(AssertionError, message):
                check_local_link(self.context, self.root / 'README.md', href)

    def test_resolves_encoded_heading_and_repeated_heading(self):
        path = self.root / 'README.md'
        path.write_text('# Title\n\n## A heading\n\n## A heading\n')
        self.assertEqual(headings(path.read_text()), {'title', 'a-heading', 'a-heading-1'})
        self.assertTrue(check_local_link(self.context, path, '#a%2Dheading-1'))

    def test_rejects_missing_title_and_unclosed_fence(self):
        for text, message in (('No heading\n', 'Expected one title'),
                              ('# Title\n\n```python\nx = 1\n', 'Unclosed fence')):
            with self.subTest(message=message), self.assertRaisesRegex(AssertionError, message):
                (self.root / 'README.md').write_text(text)
                check_markdown(self.context)

    def test_formatting_does_not_change_generation_contract(self):
        variants = [
            ('Shape [..., n].\n', 'Shape […, n].\n'),
            ('A sentence wraps\nacross lines.\n', 'A sentence wraps across lines.\n'),
            ('| Name | Value |\n| --- | --- |\n| x | 2 |\n',
             '| Name    | Value |\n| ------- | ----- |\n| x       | 2     |\n'),
        ]
        for left, right in variants:
            with self.subTest(text=left):
                self.assertEqual(semantic_tokens(left), semantic_tokens(right))

    def test_content_and_code_language_changes_are_drift(self):
        variants = [
            ('- [ ] Task\n', '- [x] Task\n'),
            ('[Spec](spec.json)\n', '[Spec](other.json)\n'),
            ('```rust\nx\n```\n', '```python\nx\n```\n'),
            ('`...`\n', '`…`\n'),
            ('| A |\n| --- |\n| 1 |\n', '| A |\n| --- |\n| 2 |\n'),
        ]
        for left, right in variants:
            with self.subTest(text=left):
                self.assertNotEqual(semantic_tokens(left), semantic_tokens(right))

    def test_generated_markers_must_be_unique_and_ordered(self):
        for text in ('END START body', 'START body END START'):
            with self.subTest(text=text), self.assertRaises(AssertionError):
                generated_matches(text, 'body', 'START', 'END')
        self.assertTrue(generated_matches('preamble START body END suffix', 'body', 'START', 'END'))
        self.assertFalse(generated_matches('START wrong END', 'body', 'START', 'END'))


class ContractBoundaries(unittest.TestCase):
    """Reject unresolved plans and preserve semantic negative-control distinctions."""

    def test_dependency_order_rejects_cycles_self_links_and_missing_tasks(self):
        invalid = [
            {'1.1.1': {'requires': ['1.1.2']}, '1.1.2': {'requires': ['1.1.1']}},
            {'1.1.1': {'requires': ['1.1.1']}},
            {'1.1.1': {'requires': ['0.1.1']}},
        ]
        for tasks in invalid:
            with self.subTest(tasks=tasks), self.assertRaises(AssertionError):
                check_dependencies(tasks)
        check_dependencies({'1.1.1': {'requires': []}, '1.1.2': {'requires': ['1.1.1']}})

    def test_duplicate_task_ids_are_not_hidden_by_indexing(self):
        task = {'id': '1.1.1', 'success': 'witness', 'sections': '1-19'}
        phases = [{'idea': 'hypothesis', 'gate': 'witness', 'steps': [
            {'number': '1.1', 'question': 'why?', 'tasks': [task, task]}]}]
        with self.assertRaisesRegex(AssertionError, 'Duplicate task'):
            collect_tasks(phases)

    def test_right_and_left_association_are_observably_distinct(self):
        self.assertEqual(right_reduce([10, 3, 2], operator.sub), 9)
        self.assertEqual(left_reduce([10, 3, 2], operator.sub), 5)
        with self.assertRaisesRegex(SemanticFailure, 'EmptyReduction'):
            right_reduce([], operator.sub)

    def test_stencil_does_not_leak_between_flattened_rows(self):
        self.assertEqual(evaluate({'kind': 'neighbour_sum', 'input': [[1, 0, 0], [0, 0, 1]]}),
                         [[0, 2, 1], [1, 2, 0]])

    def test_broadcast_and_empty_dimension_boundaries(self):
        self.assertEqual(agreement([2, 1], [3], True), [2, 3])
        self.assertEqual(agreement([0], [1], True), [0])
        with self.assertRaisesRegex(SemanticFailure, 'ShapeAgreement'):
            agreement([2], [3], True)
        with self.assertRaisesRegex(SemanticFailure, 'ShapeAgreement'):
            agreement([2, 1], [3], False)

    def test_checked_add_uses_i64_bounds(self):
        self.assertEqual(checked_add(2**63 - 1, -1), 2**63 - 2)
        for values in ((2**63 - 1, 1), (-2**63, -1)):
            with self.subTest(values=values), self.assertRaisesRegex(SemanticFailure, 'IntegerOverflow'):
                checked_add(*values)

    def test_cost_interval_distinguishes_safe_excess_and_uncertifiable(self):
        expected = ((0, 5, 'certified-within-model'), (6, 7, 'certain-excess'),
                    (0, 6, 'uncertifiable-domain'))
        for lower, upper, result in expected:
            with self.subTest(lower=lower, upper=upper):
                self.assertEqual(classify_admission({'classification': 'bound',
                                 'lower': lower, 'upper': upper, 'budget': 5}), result)
        self.assertEqual(classify_admission({'classification': 'unknown'}),
                         'runtime-obligation-or-strict-refusal')
        with self.assertRaisesRegex(AssertionError, 'Malformed cost interval'):
            classify_admission({'classification': 'bound', 'lower': 5, 'upper': 4, 'budget': 6})

    def test_cost_admission_rejects_unknown_classifications(self):
        for classification in ('bounded', 'unrecognised', ''):
            with self.subTest(classification=classification):
                with self.assertRaisesRegex(AssertionError, 'Unknown cost classification'):
                    classify_admission({'classification': classification,
                                        'lower': 0, 'upper': 0, 'budget': 5})

    def test_exact_cost_requires_equal_bounds(self):
        self.assertEqual(classify_admission({'classification': 'exact',
                         'lower': 5, 'upper': 5, 'budget': 5}), 'certified-within-model')
        with self.assertRaisesRegex(AssertionError, 'Exact cost must have equal'):
            classify_admission({'classification': 'exact',
                                'lower': 0, 'upper': 5, 'budget': 5})

    def test_cost_admission_rejects_malformed_intervals_and_budgets(self):
        for field, value in (('lower', True), ('upper', 5.0),
                             ('budget', True), ('budget', -1), ('budget', '5')):
            case = {'classification': 'bound', 'lower': 0, 'upper': 5, 'budget': 5}
            case[field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(AssertionError, 'Malformed cost'):
                    classify_admission(case)


    def test_shape_counts_and_target_width_reject_malformed_numbers(self):
        for value in (True, 1.0, -1):
            with self.subTest(field='dimension', value=value):
                with self.assertRaisesRegex(AssertionError, 'Malformed shape dimension'):
                    shape_product({'shape': [value], 'target_bits': 64})
        for value in (True, 32.0, -1, 0):
            with self.subTest(field='target_bits', value=value):
                with self.assertRaisesRegex(AssertionError, 'Malformed target width'):
                    shape_product({'shape': [1], 'target_bits': value})

    def test_shape_product_accepts_zero_and_valid_target_widths(self):
        for width in (32, 64):
            with self.subTest(width=width):
                self.assertEqual(shape_product({'shape': [0, 2**64], 'target_bits': width}), 0)
                self.assertEqual(shape_product({'shape': [], 'target_bits': width}), 1)
                self.assertEqual(shape_product({'shape': [2**width - 1], 'target_bits': width}),
                                 2**width - 1)
                self.assertEqual(shape_product({'shape': [2**width], 'target_bits': width}), 'overflow')

    def test_prefix_length_requires_nonnegative_integer(self):
        for value in (True, 4096.0, -1):
            with self.subTest(value=value), self.assertRaisesRegex(AssertionError, 'Malformed prefix length'):
                right_prefix_work({'length': value})
        for length, expected in ((0, 0), (1, 0), (3, 3)):
            with self.subTest(length=length):
                self.assertEqual(right_prefix_work({'length': length}), expected)

    def test_allocation_capacities_and_scratch_require_nonnegative_integers(self):
        for field in ('capacity', 'scratch'):
            for value in (True, 80.0, -1):
                case = {'capacities': {'source': 80},
                        'stages': [{'live': ['source', 'source'], 'scratch': 8}]}
                if field == 'capacity':
                    case['capacities']['source'] = value
                else:
                    case['stages'][0]['scratch'] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(AssertionError, 'Malformed'):
                    tracked_peak(case)
        self.assertEqual(tracked_peak({'capacities': {'source': 0},
                         'stages': [{'live': ['source', 'source'], 'scratch': 0}]}), 0)
        self.assertEqual(tracked_peak({'capacities': {'source': 80},
                         'stages': [{'live': ['source', 'source'], 'scratch': 8}]}), 88)


if __name__ == '__main__':
    unittest.main()
