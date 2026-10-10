"""Prove the comb! corpus is adequate and agrees with ADR-0007 (VO-9)."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.grammar import Parsed, Rejected, parse
from docs_validation.semantic_contracts import check_macro_grammar

ROOT = Path(__file__).resolve().parents[2]
GRAMMAR = ValidationContext(ROOT).load('spec/macro-grammar.json')
ADR_PATH = ROOT / 'docs/adrs/adr-0007-comb-macro-grammar-and-staging.md'
MUTATIONS = ('swap-mul-add', 'right-associative-pipe', 'accept-logical', 'allow-comparison-mix')


def run_with(grammar: dict | None = None, adr: str | None = None) -> None:
    """Run the grammar check with the corpus or ADR text replaced in memory."""
    context = ValidationContext(ROOT)
    original_load, original_read = context.load, Path.read_text

    def load(name: str) -> dict:
        return copy.deepcopy(grammar) if grammar is not None and name == 'spec/macro-grammar.json' else original_load(name)

    def read_text(path: Path, *args, **kwargs) -> str:
        return adr if adr is not None and path == ADR_PATH else original_read(path, *args, **kwargs)

    with patch.object(context, 'load', load), patch.object(Path, 'read_text', read_text):
        check_macro_grammar(context)


class Corpus(unittest.TestCase):
    """The corpus parses as recorded, covers every rule, and distinguishes each seeded mutation."""

    def test_committed_corpus_passes(self):
        check_macro_grammar(ValidationContext(ROOT))

    def test_each_seeded_mutation_changes_an_entry(self):
        for mutation in MUTATIONS:
            with self.subTest(mutation=mutation):
                changed = [entry['id'] for entry in GRAMMAR['corpus']
                           if parse(entry['source'], GRAMMAR, frozenset({mutation})) != parse(entry['source'], GRAMMAR)]
                self.assertTrue(changed, f'mutation {mutation} must change at least one corpus outcome')

    def test_pipe_is_lowest_and_left_associative(self):
        self.assertEqual(parse('a + b |> c |> d', GRAMMAR), Parsed('(|> (|> (+ a b) c) d)'),
                         '|> binds looser than + and groups to the left')

    def test_comparison_mix_is_rejected_in_both_nestings(self):
        for source in ('a | b == c', 'a == b & c'):
            with self.subTest(source=source):
                self.assertEqual(parse(source, GRAMMAR), Rejected('comparison-bitwise-mix'), 'mixing needs parentheses')

    def test_wrong_recorded_tree_fails(self):
        grammar = copy.deepcopy(GRAMMAR)
        grammar['corpus'][4]['tree'] = '(* (+ a b) c)'
        with self.assertRaisesRegex(AssertionError, 'Grammar corpus G05 expected'):
            run_with(grammar=grammar)

    def test_missing_rule_coverage_fails(self):
        grammar = copy.deepcopy(GRAMMAR)
        grammar['corpus'] = [entry for entry in grammar['corpus'] if 'range' not in entry['covers']]
        with self.assertRaisesRegex(AssertionError, 'Grammar corpus misses range'):
            run_with(grammar=grammar)

    def test_precedence_table_must_agree_with_adr_0007(self):
        text = ADR_PATH.read_text(encoding='utf-8')
        swapped = text.replace('| Shift          |', '| Shiftx         |').replace('`<<` `>>`', '`>>` `<<`')
        self.assertNotEqual(swapped, text, 'the control must edit the table')
        with self.assertRaisesRegex(AssertionError, 'disagrees with the ADR-0007 precedence table'):
            run_with(adr=swapped)


if __name__ == '__main__':
    unittest.main()
