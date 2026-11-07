"""Prove a roadmap tick cannot outrun a candidate ADR subject deferred to it."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_docs import collect_checks
from docs_validation.candidate_deferral import (
    check_candidate_deferral, deferred_candidates, roadmap_items, ticked_items,
)
from docs_validation.context import ValidationContext
from docs_validation.revision_reader import git_head_revision
from export_roadmap import export_text

ROOT = Path(__file__).resolve().parents[2]
CHECK = 'candidate-deferral'


def candidate(candidate_id: str, disposition: dict, subject: str = 'Example subject') -> dict:
    """Build the register fragment one candidate needs, with only the fields this check reads."""
    return {'id': candidate_id, 'subject': subject, 'disposition': disposition}


def deferred(candidate_id: str, item: str, subject: str = 'Example subject') -> dict:
    """Build a candidate deferred to one roadmap item."""
    return candidate(candidate_id, {'kind': 'deferred', 'roadmap_item': item}, subject)


def settled(candidate_id: str) -> dict:
    """Build a candidate settled by an ADR, which no deferral constrains."""
    return candidate(candidate_id, {'kind': 'adr', 'adrs': ['ADR-0001']})


def roadmap_export(*steps: dict) -> dict:
    """Build a roadmap export whose single phase holds the supplied steps."""
    return {'phases': [{'steps': list(steps)}]}


def roadmap_step(number: str, *statuses: str) -> dict:
    """Build a step whose tasks are numbered from the step and take the supplied statuses."""
    tasks = [{'id': f'{number}.{index + 1}', 'status': status}
             for index, status in enumerate(statuses)]
    return {'number': number, 'tasks': tasks}


class TickVocabulary(unittest.TestCase):
    """The tick vocabulary distinguishes whole steps from partly finished ones."""

    def test_a_step_counts_as_ticked_only_when_every_task_beneath_it_is(self):
        """Report a step identifier as ticked only when all of its tasks are ticked."""
        cases = ((('open', 'open'), set()), (('done', 'open'), {'2.4.1'}),
                 (('done', 'done'), {'2.4', '2.4.1', '2.4.2'}))
        for statuses, expected in cases:
            with self.subTest(statuses=statuses):
                self.assertEqual(ticked_items(roadmap_export(roadmap_step('2.4', *statuses))), expected,
                                 'a step counts as ticked only when all of its tasks are')

    def test_every_declared_identifier_is_known_before_the_roadmap_is_consulted(self):
        """Declare step and task identifiers so a typo in a deferral is not read as open work."""
        declared = roadmap_items(roadmap_export(roadmap_step('2.4', 'open')))
        self.assertEqual(declared, {'2.4', '2.4.1'},
                         'both the step and its task are declared identifiers')

    def test_only_deferred_candidates_are_returned(self):
        """Keep ADR-settled candidates out of the deferral sweep entirely."""
        register = {'candidate_adrs': [settled('CA1'), deferred('CA3', '1.2.1')]}
        self.assertEqual([entry['id'] for entry in deferred_candidates(register)], ['CA3'],
                         'an ADR disposition is not a deferral and constrains no tick')


class DeferralCheck(unittest.TestCase):
    """Each deferral fault is rejected for its own reason."""

    def setUp(self):
        """Create an isolated repository holding the roadmap, deferrals, and nothing else."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'spec').mkdir()

    def write(self, roadmap_value: dict, candidates: list[dict]) -> ValidationContext:
        """Write the two inputs and return a context rooted at the temporary repository."""
        (self.root / 'spec/roadmap.json').write_text(json.dumps(roadmap_value), encoding='utf-8')
        (self.root / 'spec/decisions.json').write_text(
            json.dumps({'candidate_adrs': candidates}), encoding='utf-8')
        return ValidationContext(self.root)

    def test_unticked_deferrals_pass_and_record_what_was_compared(self):
        """Accept deferrals whose items are declared and still open."""
        context = self.write(roadmap_export(roadmap_step('1.2', 'open', 'open')),
                             [deferred('CA3', '1.2.1')])
        check_candidate_deferral(context)
        self.assertEqual([row['check'] for row in context.results], [CHECK],
                         'a passing check must record its own result')
        self.assertEqual(context.results[0]['count'], 1, 'the result must count the deferrals compared')

    def test_ticked_task_names_the_outrun_candidate(self):
        """Reject a tick of the very item a candidate is deferred to."""
        context = self.write(roadmap_export(roadmap_step('1.2', 'done', 'open')),
                             [deferred('CA3', '1.2.1', 'Backend and cell separation')])
        with self.assertRaisesRegex(
                AssertionError,
                r'CA3 \(Backend and cell separation\) is deferred to 1\.2\.1, which is ticked'):
            check_candidate_deferral(context)

    def test_a_whole_step_is_one_item(self):
        """Reject a tick when a deferral names the step rather than a task beneath it."""
        context = self.write(roadmap_export(roadmap_step('2.4', 'done', 'done')),
                             [deferred('CA7', '2.4')])
        with self.assertRaisesRegex(AssertionError, r'CA7 .* is deferred to 2\.4, which is ticked'):
            check_candidate_deferral(context)

    def test_a_partly_finished_step_leaves_the_deferral_standing(self):
        """Do not accuse a deferral of being stale while its step still has open work."""
        context = self.write(roadmap_export(roadmap_step('2.4', 'done', 'open')),
                             [deferred('CA7', '2.4')])
        check_candidate_deferral(context)
        self.assertEqual(context.results[0]['count'], 1, 'the partly finished step must still be compared')

    def test_an_unknown_item_fails_rather_than_passing_vacuously(self):
        """Reject a deferral naming an item the export does not declare."""
        context = self.write(roadmap_export(roadmap_step('1.2', 'open')), [deferred('CA9', '9.9.9')])
        with self.assertRaisesRegex(
                AssertionError, r'CA9 is deferred to 9\.9\.9, which the roadmap does not declare'):
            check_candidate_deferral(context)

    def test_every_outrun_candidate_is_named(self):
        """Name each offending deferral rather than stopping at the first."""
        context = self.write(roadmap_export(roadmap_step('1.2', 'done')),
                             [deferred('CA3', '1.2.1'), deferred('CA5', '1.2.1', 'Shared semantic kernel')])
        with self.assertRaisesRegex(AssertionError, r'CA3 .*CA5 \(Shared semantic kernel\)'):
            check_candidate_deferral(context)


class CommittedDeferrals(unittest.TestCase):
    """The committed register and roadmap agree, and a trial tick in a copy fails."""

    def test_committed_deferrals_pass_and_the_check_runs_before_closure(self):
        """Check the committed inputs through the composed checker."""
        context = ValidationContext(ROOT, source_revision=git_head_revision(ROOT))
        collect_checks(context)
        names = [row['check'] for row in context.results]
        self.assertIn(CHECK, names, 'the composed checker must run the deferral check')
        self.assertLess(names.index(CHECK), names.index('roadmap-status'),
                        'the deferral check must run before roadmap closure reports ticks')
        self.assertTrue(deferred_candidates(ValidationContext(ROOT).load('spec/decisions.json')),
                        'the committed register must keep at least one deferral for this check to guard')

    def test_trial_tick_in_a_temporary_copy_fails(self):
        """Tick 1.2.1 in a copy of the canonical roadmap and require the committed register to reject it."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / 'spec').mkdir()
        (root / 'docs').mkdir()
        shutil.copyfile(ROOT / 'spec/decisions.json', root / 'spec/decisions.json')
        text = (ROOT / 'docs/roadmap.md').read_text(encoding='utf-8')
        trialled = text.replace('- [ ] 1.2.1.', '- [x] 1.2.1.', 1)
        self.assertNotEqual(trialled, text, 'the trial tick must change the canonical roadmap')
        (root / 'docs/roadmap.md').write_text(trialled, encoding='utf-8')
        (root / 'spec/roadmap.json').write_text(export_text(trialled), encoding='utf-8')
        with self.assertRaises(AssertionError) as raised:
            check_candidate_deferral(ValidationContext(root))
        message = str(raised.exception)
        for candidate_id in ('CA3', 'CA5'):
            self.assertIn(f'{candidate_id} (', message,
                          'every candidate still deferred to 1.2.1 must be named by the trial tick')


if __name__ == '__main__':
    unittest.main()
