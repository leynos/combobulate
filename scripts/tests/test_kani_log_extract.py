"""Require the Kani extractor to read every committed log to its recorded facts (VO-11a).

The extractor is the gate's only view of what a proof run actually printed, so
the corpus cases pin the facts each committed log yields. That is what makes a
log's meaning a committed claim rather than this suite's opinion: the
expectations file records what every log must produce, and this module compares
the parser with it field by field.

The mutation half of VO-11a — truncated, deleted, duplicated, interleaved, and
re-counted logs — lives in :mod:`test_kani_log_mutations`, which uses the same
helpers from :mod:`kani_log_text_fixtures`. Splitting there keeps each module
focused: this one asks "does the parser read a good log correctly?", the other
asks "does it refuse a broken one structurally?".

Examples
--------
>>> sorted(corpus.log_names())[0]
'counterexample'
>>> corpus.decision_for('truncated').outcome
'tool-error'
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kani_corpus_fixtures as corpus
from kani_log_text_fixtures import EXPECTED, blocks_of, refused, table_blocks


class CorpusFacts(unittest.TestCase):
    """Require every committed log to yield exactly the facts it is recorded to have."""

    def test_every_committed_log_is_accounted_for(self):
        """Cover the corpus exactly: one expectation per log, and no extra."""
        self.assertEqual(sorted(corpus.log_names()), sorted(EXPECTED['logs']),
                         'the expectations must name every committed log and nothing else')

    def test_every_log_yields_its_recorded_facts(self):
        """Compare each log's banner, format, summary, blocks, and checks with the table."""
        for name in corpus.log_names():
            with self.subTest(log=name):
                expected = EXPECTED['logs'][name]
                if 'refused' in expected:
                    self.assertEqual(refused(corpus.log_text(name)), expected['refused'],
                                     f'{name} must be refused for its recorded reason')
                    continue
                parsed = corpus.parse_log(name)
                self.assertEqual(parsed.banner_version, expected['banner'], f'{name} must carry its banner')
                self.assertEqual(parsed.format, expected['format'], f'{name} must report its format')
                self.assertEqual(parsed.unsupported_constructs, tuple(expected['unsupported']),
                                 f'{name} must report the constructs Kani named')
                self.assert_recorded_summary(name, parsed.manual, expected['manual'])
                self.assertEqual(blocks_of(name), table_blocks(expected),
                                 f'{name} must yield its recorded per-harness facts')

    def assert_recorded_summary(self, name, manual, expected):
        """Compare one log's manual harness summary, allowing an inventory to have none."""
        if expected is None:
            self.assertIsNone(manual, f'{name} is an inventory and must carry no manual summary')
            return
        self.assertIsNotNone(manual, f'{name} must carry a manual harness summary')
        self.assertEqual((manual.verified, manual.failures, manual.total, manual.failed),
                         (expected['verified'], expected['failures'], expected['total'],
                          tuple(expected['failed'])),
                         f'{name} must carry its recorded manual summary')

    def test_a_truncated_log_is_refused_strictly(self):
        """Refuse the corpus's killed run, which ends inside a harness block."""
        self.assertIn('truncated', refused(corpus.log_text('truncated')),
                      'the killed run must be refused as truncated')

    def test_the_inventory_log_carries_no_verdicts(self):
        """Read ``kani list`` output as an inventory rather than a run."""
        parsed = corpus.parse_log('list')
        self.assertEqual((parsed.format, parsed.blocks), ('inventory', ()),
                         'kani list output must carry no harness blocks')
        self.assertEqual(parsed.unsupported_constructs, ('TerminatorKind::InlineAsm',),
                         'the inventory must still report the construct warning')

    def test_the_should_panic_run_keeps_its_note(self):
        """Record Kani's note, which is what excuses the failed assertion."""
        block = corpus.parse_log('expected_panic').blocks[0]
        self.assertEqual((block.verdict, block.panics_as_expected), ('SUCCESSFUL', True),
                         'a should_panic run must record the note it was excused by')

    def test_a_failure_records_where_it_happened(self):
        """Keep the source location of each failure, the fact a record cannot invent."""
        block = corpus.parse_log('counterexample').blocks[0]
        self.assertEqual([(item.path, item.line) for item in block.failures],
                         [('src/harnesses.rs', 18)], 'the failure must carry its source location')

    def test_the_unwinding_warning_is_recorded_on_the_block_it_names(self):
        """Require Kani's unwinding note, which is the run's own statement of the bound.

        The extract table records the flag but the decision does not read it, so
        this is the only assertion standing between the flag and silent removal.
        Without it, an unwinding failure would be recognized solely by the
        ``unwind`` suffix on the check identifier, and the ``[Kani] info:`` line
        Kani prints about it would be dropped without anything noticing.
        """
        parsed = corpus.parse_log('insufficient_unwind')
        self.assertEqual([item.unwinding_reported for item in parsed.blocks], [True],
                         'a log carrying the unwinding note must record it on its block')
        self.assertEqual([item.kind for item in parsed.blocks[0].checks if item.status == 'FAILURE'],
                         ['unwind'], 'the block the note names must own the failed unwinding check')


if __name__ == '__main__':
    unittest.main()
