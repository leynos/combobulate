"""Check the corpus runner's decision path against the committed logs.

``scripts/check_kani_corpus.py`` runs Kani and decides each fresh log. These
tests feed it the committed logs of the same runs instead, so the comparison it
makes in CI is shown to accept the decisions recorded for them and to refuse a
log whose decision differs, without a Kani installation.
"""

import json
import unittest
from pathlib import Path

import check_kani_corpus as corpus

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / 'scripts/tests/fixtures/kani_logs'


def _runs() -> list[dict]:
    """Return the corpus run definitions that carry a verdict."""
    document = json.loads((corpus.CORPUS / 'harnesses.json').read_text(encoding='utf-8'))
    return [run for run in document['runs'] if run['id'] not in corpus.NOT_VERDICT_RUNS]


def _manifest() -> dict:
    """Return the corpus harness manifest document."""
    return json.loads((corpus.CORPUS / 'harness-manifest.json').read_text(encoding='utf-8'))


def _recorded() -> dict:
    """Return the decisions recorded for the committed logs."""
    return json.loads(corpus.EXPECTED.read_text(encoding='utf-8'))['decisions']


class SelectionTests(unittest.TestCase):
    """The harness selection comes from the run's arguments."""

    def test_each_harness_flag_names_one_harness(self) -> None:
        """Repeated flags select several harnesses in order."""
        arguments = ['--harness', 'a::x', '--exact', '--harness', 'a::y']
        self.assertEqual(corpus.selected_harnesses(arguments), ('a::x', 'a::y'))

    def test_no_flag_selects_the_whole_crate(self) -> None:
        """A run with no ``--harness`` selects nothing in particular."""
        self.assertEqual(corpus.selected_harnesses(['--verbose']), ())


class CommittedLogTests(unittest.TestCase):
    """Every verdict-bearing run decides as recorded when read from its log."""

    def test_each_committed_log_decides_as_recorded(self) -> None:
        """The runner's decision for a run's committed log equals the record."""
        recorded, manifest = _recorded(), _manifest()
        for run in _runs():
            with self.subTest(run=run['id']):
                text = (LOGS / f"{run['id']}.log").read_text(encoding='utf-8')
                decision = corpus.decide_log(
                    text, corpus.selected_harnesses(run['arguments']), manifest)
                self.assertEqual(
                    corpus.observed_decision(decision),
                    corpus.recorded_decision(recorded[run['id']]))

    def test_a_log_that_is_not_kani_output_is_a_tool_error(self) -> None:
        """Output that is not a Kani log must decide as a tool error, never pass."""
        decision = corpus.decide_log('not a log', (), _manifest())
        self.assertEqual(decision.outcome, 'tool-error')

    def test_a_different_run_does_not_match_the_record(self) -> None:
        """A counterexample log must not satisfy the record for a verified run."""
        recorded, manifest = _recorded(), _manifest()
        text = (LOGS / 'counterexample.log').read_text(encoding='utf-8')
        decision = corpus.decide_log(text, ('harnesses::counterexample',), manifest)
        self.assertNotEqual(
            corpus.observed_decision(decision),
            corpus.recorded_decision(recorded['verified']))

    def test_the_runner_covers_every_corpus_harness(self) -> None:
        """The nine corpus harnesses are each selected by at least one run."""
        selected = {name for run in _runs() for name in corpus.selected_harnesses(run['arguments'])}
        names = {entry['name'] for entry in _manifest()['harnesses']}
        self.assertEqual(selected, names)


if __name__ == '__main__':
    unittest.main()
