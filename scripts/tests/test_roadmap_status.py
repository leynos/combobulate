"""Prove roadmap ticks are backed by evidence (VO-4: MS-3, MS-4, and closure soundness)."""
from __future__ import annotations

import copy
import datetime
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.closure_evidence import ClosureEvidence
from docs_validation.evidence_gate import Level
from docs_validation.revision_reader import git_head_revision
from check_docs import collect_checks
from docs_validation.roadmap_status import (
    ArtefactProblem, CheckResult, ClosureInputs, artefact_resolver, closure_failures, component_failure, index_completions,
    index_components, task_closure,
)

ROOT = Path(__file__).resolve().parents[2]
ACCEPTED = {'id': 'D01', 'lifecycle': 'accepted'}
ARTEFACT = 'docs/adrs/adr-0002-governance-authority.md'


def task(task_id: str, requires: list[str], status: str = 'open') -> dict:
    """Build a minimal exported task."""
    return {'id': task_id, 'requires': requires, 'status': status}


def chain() -> dict[str, dict]:
    """Return 1.1.1 -> 1.1.2 -> 1.1.3, all open."""
    return {'1.1.1': task('1.1.1', []), '1.1.2': task('1.1.2', ['1.1.1']), '1.1.3': task('1.1.3', ['1.1.2'])}


def diamond() -> dict[str, dict]:
    """Return 1.1.1 -> {1.1.2, 1.1.3} -> 1.1.4, all open."""
    return {'1.1.1': task('1.1.1', []), '1.1.2': task('1.1.2', ['1.1.1']), '1.1.3': task('1.1.3', ['1.1.1']),
            '1.1.4': task('1.1.4', ['1.1.2', '1.1.3'])}


def completions(tasks: dict[str, dict]) -> dict[str, dict]:
    """Give every task a completion record citing an accepted decision and an existing artefact."""
    return {task_id: {'task': task_id, 'decisions': ['D01'], 'artefacts': [ARTEFACT]} for task_id in tasks}


def component(component_id: str, source: str, accepts: list[str] | None = None) -> dict:
    """Build a component whose fields agree with its identifier."""
    owner_method, task_id = component_id.split('@')
    return {'id': component_id, 'method': owner_method.split('.')[1], 'task': task_id,
            'accepts': accepts or ['tested'], 'evidence_source': source, 'evidence': []}


def inputs(tasks: dict[str, dict], **overrides: object) -> ClosureInputs:
    """Build closure inputs in which every condition holds unless overridden."""
    values = {'tasks': tasks, 'completions': completions(tasks), 'decisions': {'D01': ACCEPTED},
              'components': {}, 'check_results': (CheckResult('evidence-gate', 'pass', 'r1'),),
              'artefact_problem': lambda artefact: None if artefact == ARTEFACT else ArtefactProblem('is missing'),
              'current_source_revision': 'r1'}
    values.update(overrides)
    return ClosureInputs(**values)


def ticked(tasks: dict[str, dict], *task_ids: str) -> dict[str, dict]:
    """Return a copy with the named tasks ticked."""
    edited = copy.deepcopy(tasks)
    for task_id in task_ids:
        edited[task_id]['status'] = 'done'
    return edited


class TaskClosure(unittest.TestCase):
    """MS-4: a tick needs ticked prerequisites, accepted decisions, artefacts, and satisfied components."""

    def assert_rejected(self, closure: ClosureInputs, message: str) -> None:
        """Assert that closure fails with the requested diagnostic."""
        with self.assertRaisesRegex(AssertionError, message):
            task_closure(closure)

    def test_fully_supported_ticks_pass_on_chain_and_diamond(self):
        """Accept every tick when both generated roadmap shapes have complete evidence."""
        for name, shape in (('chain', chain()), ('diamond', diamond())):
            with self.subTest(shape=name):
                done = ticked(shape, *shape)
                self.assertEqual(task_closure(inputs(done))[0], list(shape), 'every supported tick is accepted')

    def test_tick_with_open_prerequisite_fails(self):
        """Reject a tick when a chain or diamond prerequisite remains open."""
        for name, shape, target, missing in (('chain', chain(), '1.1.3', '1.1.2'),
                                             ('diamond', diamond(), '1.1.4', '1.1.3')):
            with self.subTest(shape=name):
                done = ticked(shape, *(task_id for task_id in shape if task_id != missing))
                self.assert_rejected(inputs(done), f'Task {target} is ticked but prerequisite {missing} is not ticked')

    def test_tick_citing_proposed_or_superseded_decision_fails(self):
        """Reject completion evidence that cites a decision which no longer binds."""
        for lifecycle in ('proposed', 'superseded', 'withdrawn'):
            with self.subTest(lifecycle=lifecycle):
                closure = inputs(ticked(chain(), '1.1.1'), decisions={'D01': {'id': 'D01', 'lifecycle': lifecycle}})
                self.assert_rejected(closure, f'decision D01 is {lifecycle}, not accepted')

    def test_tick_without_completion_record_fails(self):
        """Reject a tick with no entry in the completion register."""
        closure = inputs(ticked(chain(), '1.1.1'), completions={})
        self.assert_rejected(closure, 'Task 1.1.1 is ticked but no completion record')

    def test_tick_with_unresolvable_artefact_fails(self):
        """Reject a tick when its completion artefact cannot be resolved."""
        closure = inputs(ticked(chain(), '1.1.1'),
                         artefact_problem=lambda artefact: ArtefactProblem('does not resolve'))
        self.assert_rejected(closure, f'artefact {ARTEFACT} does not resolve')

    def test_record_sourced_component_fails_closed(self):
        """Keep record-sourced components unsatisfied until evidence admission exists."""
        components = {'1.1.1': [component('PF14.proof@1.1.1', 'record', ['proof'])]}
        closure = inputs(ticked(chain(), '1.1.1'), components=components)
        self.assert_rejected(closure, 'component PF14.proof@1.1.1 has no evidence record')

    def test_checker_component_needs_its_check_to_pass_in_this_run(self):
        """Use this run's check result to satisfy a checker-sourced component."""
        components = {'1.1.1': [component('PF14.structural@1.1.1', 'checker:evidence-gate')]}
        self.assertEqual(task_closure(inputs(ticked(chain(), '1.1.1'), components=components))[0], ['1.1.1'],
                         'a passing evidence-gate check satisfies the structural component')
        closure = inputs(ticked(chain(), '1.1.1'), components=components, check_results=())
        self.assert_rejected(closure, 'needs the latest result for check evidence-gate to pass in this run')

    def test_checker_component_uses_latest_current_run_result(self):
        """Do not let an earlier pass override a later failure for the same check."""
        components = {'1.1.1': [component('PF14.structural@1.1.1', 'checker:evidence-gate')]}
        results = (CheckResult('evidence-gate', 'pass', 'r1'), CheckResult('evidence-gate', 'fail', 'r1'))
        closure = inputs(ticked(chain(), '1.1.1'), components=components, check_results=results)
        self.assert_rejected(closure, 'needs the latest result for check evidence-gate to pass in this run')

    def test_checker_component_rejects_a_result_from_another_binding(self):
        """Require the current-run check result to inspect the current source revision."""
        components = {'1.1.1': [component('PF14.structural@1.1.1', 'checker:evidence-gate')]}
        results = (CheckResult('evidence-gate', 'pass', 'older-revision'),)
        closure = inputs(ticked(chain(), '1.1.1'), components=components, check_results=results)
        self.assert_rejected(closure, 'is not bound to current source revision r1')

    def test_checker_component_fails_closed_without_current_source_revision(self):
        """Do not accept checker evidence when its source binding cannot be identified."""
        components = {'1.1.1': [component('PF14.structural@1.1.1', 'checker:evidence-gate')]}
        closure = inputs(ticked(chain(), '1.1.1'), components=components, current_source_revision=None)
        self.assert_rejected(closure, 'cannot determine the current source revision')

    def test_checker_component_requires_tested_acceptance(self):
        """Keep checker output at tested even if a component accepts only proof."""
        proof_only = component('PF14.structural@1.1.1', 'checker:evidence-gate', ['proof'])
        failure = component_failure(proof_only, (CheckResult('evidence-gate', 'pass', 'r1'),), {}, 'r1')
        self.assertEqual(failure, 'component PF14.structural@1.1.1 does not accept tested checker evidence',
                         'a checker result cannot satisfy a proof-only component')

    def test_admitted_record_satisfies_and_a_counterexample_reopens(self):
        """Close on admitted proof evidence and reopen when a current counterexample appears."""
        components = {'1.1.1': [component('PF14.proof@1.1.1', 'record', ['proof'])]}
        verified = ClosureEvidence('PF14.proof@1.1.1', datetime.date(2026, 10, 10), 'r1',
                                   'verified', True, Level.PROOF, ())
        evidence = {'PF14.proof@1.1.1': [verified]}
        closure = inputs(ticked(chain(), '1.1.1'), components=components, evidence=evidence)
        self.assertEqual(task_closure(closure)[0], ['1.1.1'], 'an admitted proof record satisfies the component')
        counterexample = ClosureEvidence('PF14.proof@1.1.1', datetime.date(2026, 10, 9), 'r1',
                                         'counterexample', True, Level.REJECTED, ('outcome-counterexample',))
        evidence['PF14.proof@1.1.1'].append(counterexample)
        self.assert_rejected(inputs(ticked(chain(), '1.1.1'), components=components, evidence=evidence),
                             'has a counterexample at source revision r1')

    def test_checker_counterexample_vetoes_a_passing_check(self):
        """A current-source counterexample reopens checker-backed closure at any admission level."""
        component_id = 'PF14.structural@1.1.1'
        components = {'1.1.1': [component(component_id, 'checker:evidence-gate')]}
        counterexample = ClosureEvidence(component_id, datetime.date(2026, 10, 9), 'r1',
                                         'counterexample', True, Level.REJECTED, ('outcome-counterexample',))
        evidence = {component_id: [counterexample]}
        closure = inputs(ticked(chain(), '1.1.1'), components=components, evidence=evidence)
        self.assert_rejected(closure, 'has a counterexample at source revision r1')

    def test_checker_counterexample_for_an_older_revision_does_not_veto(self):
        """Apply the checker veto only to the revision whose current check passed."""
        component_id = 'PF14.structural@1.1.1'
        components = {'1.1.1': [component(component_id, 'checker:evidence-gate')]}
        counterexample = ClosureEvidence(component_id, datetime.date(2026, 10, 9), 'older-revision',
                                         'counterexample', True, Level.REJECTED, ('outcome-counterexample',))
        evidence = {component_id: [counterexample]}
        closure = inputs(ticked(chain(), '1.1.1'), components=components, evidence=evidence)
        self.assertEqual(task_closure(closure)[0], ['1.1.1'],
                         'an older revision counterexample does not invalidate the current run')

    def test_record_below_the_accepted_level_fails(self):
        """Keep evidence below the component's accepted level from closing the task."""
        components = {'1.1.1': [component('PF14.proof@1.1.1', 'record', ['proof'])]}
        bounded = ClosureEvidence('PF14.proof@1.1.1', datetime.date(2026, 10, 10), 'r1',
                                  'verified', True, Level.BOUNDED, ())
        evidence = {'PF14.proof@1.1.1': [bounded]}
        self.assert_rejected(inputs(ticked(chain(), '1.1.1'), components=components, evidence=evidence),
                             'evidence is bounded')

    def test_same_day_latest_records_fail_closed(self):
        """Reject ambiguous evidence when several current records share the latest date."""
        component_id = 'PF14.proof@1.1.1'
        components = {'1.1.1': [component(component_id, 'record', ['proof'])]}
        first = ClosureEvidence(component_id, datetime.date(2026, 10, 10), 'r1', 'verified', True, Level.PROOF, ())
        evidence = {component_id: [first, first]}
        failures = closure_failures('1.1.1', inputs(ticked(chain(), '1.1.1'), components=components,
                                                   evidence=evidence))
        self.assertIn(f'component {component_id} has 2 records on latest recorded_on date 2026-10-10', failures,
                      'same-day latest records are ambiguous and cannot close a task')

    def test_later_stale_binding_record_does_not_supersede_current_evidence(self):
        """Select the latest record only after excluding another binding's evidence."""
        component_id = 'PF14.proof@1.1.1'
        components = {'1.1.1': [component(component_id, 'record', ['proof'])]}
        current = ClosureEvidence(component_id, datetime.date(2026, 10, 10), 'r1', 'verified', True, Level.PROOF, ())
        stale = ClosureEvidence(component_id, datetime.date(2026, 10, 11), 'r2', 'verified',
                                False, Level.REJECTED, ('binding-stale',))
        evidence = {component_id: [current, stale]}
        closure = inputs(ticked(chain(), '1.1.1'), components=components, evidence=evidence)
        self.assertEqual(task_closure(closure)[0], ['1.1.1'],
                         'a later record at a different binding must not supersede current evidence')

    def test_same_date_stale_record_does_not_make_current_evidence_ambiguous(self):
        """Limit latest-date ambiguity to the registered current binding."""
        component_id = 'PF14.proof@1.1.1'
        components = {'1.1.1': [component(component_id, 'record', ['proof'])]}
        current = ClosureEvidence(component_id, datetime.date(2026, 10, 10), 'r1', 'verified', True, Level.PROOF, ())
        stale = ClosureEvidence(component_id, datetime.date(2026, 10, 10), 'r2', 'verified',
                                False, Level.REJECTED, ('binding-stale',))
        evidence = {component_id: [current, stale]}
        closure = inputs(ticked(chain(), '1.1.1'), components=components, evidence=evidence)
        self.assertEqual(task_closure(closure)[0], ['1.1.1'],
                         'a same-day stale record must not make the current binding ambiguous')

    def test_supported_but_unticked_task_is_reported_not_failed(self):
        """Report supported open work as eligible while keeping it unticked."""
        ticks, eligible = task_closure(inputs(ticked(chain(), '1.1.1')))
        self.assertEqual((ticks, eligible), (['1.1.1'], ['1.1.2']), 'only the next task becomes eligible')

    def test_closure_names_each_open_prerequisite(self):
        """Name the prerequisite that prevents an otherwise supported task from closing."""
        failures = closure_failures('1.1.2', inputs(ticked(chain(), '1.1.2')))
        self.assertIn('prerequisite 1.1.1 is not ticked', failures, 'closure soundness names the open prerequisite')


class ComponentsAndCompletions(unittest.TestCase):
    """MS-3 inputs are validated before closure reads them."""

    def obligation(self, *components: dict) -> dict:
        """Build a PF14 contract requiring components for both linked tasks."""
        return {'id': 'PF14', 'tasks': ['1.1.4', '3.4.1'], 'components': list(components)}

    def test_every_obligation_task_needs_a_component(self):
        """Require every linked task to have a component in the obligation."""
        with self.assertRaisesRegex(AssertionError, 'PF14 has no component for tasks 3.4.1'):
            index_components([self.obligation(component('PF14.structural@1.1.4', 'checker:evidence-gate'))])

    def test_component_must_belong_to_its_obligation(self):
        """Reject a component whose owner differs from the enclosing obligation."""
        with self.assertRaisesRegex(AssertionError, 'does not belong to PF14'):
            index_components([self.obligation(component('PF13.structural@1.1.4', 'checker:evidence-gate'))])

    def test_component_fields_must_agree_with_identity(self):
        """Reject component metadata that disagrees with its encoded identity."""
        broken = component('PF14.structural@1.1.4', 'checker:evidence-gate') | {'method': 'proof'}
        with self.assertRaisesRegex(AssertionError, 'disagrees with its method or task fields'):
            index_components([self.obligation(broken)])

    def test_component_cannot_accept_restricted(self):
        """Reject restricted as a component admission level."""
        broken = component('PF14.structural@1.1.4', 'record', ['restricted'])
        with self.assertRaisesRegex(AssertionError, 'must accept a non-empty subset'):
            index_components([self.obligation(broken)])

    def test_checker_component_must_accept_tested(self):
        """Require checker-sourced components to admit tested evidence."""
        broken = component('PF14.structural@1.1.4', 'checker:evidence-gate', ['proof'])
        with self.assertRaisesRegex(AssertionError, 'must accept the tested level'):
            index_components([self.obligation(broken)])

    def test_completion_record_must_cite_known_decisions(self):
        """Reject a completion record that names a decision absent from the register."""
        with self.assertRaisesRegex(AssertionError, 'cites unknown decisions D99'):
            index_completions({'tasks': [{'task': '1.1.1', 'decisions': ['D99'], 'artefacts': [ARTEFACT]}]},
                              chain(), {'D01': ACCEPTED})

    def test_completion_record_may_cite_no_decisions(self):
        """Allow an empty citation list when no register decision governs the task."""
        record = {'task': '1.1.1', 'decisions': [], 'artefacts': [ARTEFACT]}
        indexed = index_completions({'tasks': [record]}, chain(), {})
        self.assertEqual(indexed, {'1.1.1': record},
                         'an ungoverned task must not need an invented decision citation')


class RealRoadmap(unittest.TestCase):
    """The committed roadmap passes closure, and PF14.structural@1.1.4 is wired to the evidence gate."""

    def test_committed_roadmap_precedes_package_policy_that_consumes_it(self):
        """Validate task closure before package policy consumes that result."""
        context = ValidationContext(ROOT, source_revision=git_head_revision(ROOT))
        collect_checks(context)
        checks = [row['check'] for row in context.results]
        self.assertIn('roadmap-status', checks, 'the composed checker must run roadmap closure')
        self.assertIn('package-policy', checks, 'the composed checker must run package policy')
        self.assertLess(checks.index('roadmap-status'), checks.index('package-policy'),
                        'package policy must run after validated roadmap closure')

    def test_artefact_outside_the_repository_does_not_resolve(self):
        """Keep artefact resolution within the repository and require any anchor to exist."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repository'
            (root / 'docs').mkdir(parents=True)
            (root / 'docs/guide.md').write_text('# Guide\n', encoding='utf-8')
            outside = Path(directory) / 'outside.md'
            outside.write_text('# Outside\n', encoding='utf-8')
            resolve = artefact_resolver(ValidationContext(root))
            self.assertIsNone(resolve('docs/guide.md#guide'), 'an in-repository heading resolves')
            relative_problem = resolve('../outside.md')
            assert relative_problem is not None, 'an escaped relative artefact returns a problem'
            self.assertIn('outside the repository', relative_problem.detail,
                          'a relative path escaping the root is rejected')
            absolute_problem = resolve(str(outside))
            assert absolute_problem is not None, 'an escaped absolute artefact returns a problem'
            self.assertIn('outside the repository', absolute_problem.detail,
                          'an absolute path outside the root is rejected')
            anchor_problem = resolve('docs/guide.md#no-such-heading')
            assert anchor_problem is not None, 'a missing heading anchor returns a problem'
            self.assertIn('no heading anchor', anchor_problem.detail,
                          'a missing anchor is reported')

    def test_anchored_non_utf8_artefact_does_not_resolve(self) -> None:
        """Report undecodable anchored artefacts as unresolved without rejecting their path."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repository'
            (root / 'docs').mkdir(parents=True)
            (root / 'docs/binary.dat').write_bytes(b'\xff')
            resolve = artefact_resolver(ValidationContext(root))
            self.assertIsNone(resolve('docs/binary.dat'), 'an unanchored in-root file resolves')
            self.assertEqual(resolve('docs/binary.dat#heading'),
                             ArtefactProblem('is not valid UTF-8 text'),
                             'an undecodable file cannot satisfy an anchor')

    def test_artefact_read_failure_returns_a_named_problem(self) -> None:
        """Translate an expected file read failure into the resolver contract."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repository'
            (root / 'docs').mkdir(parents=True)
            (root / 'docs/guide.md').write_text('# Guide\n', encoding='utf-8')
            resolve = artefact_resolver(ValidationContext(root))
            with patch.object(Path, 'read_text', side_effect=OSError('read blocked')):
                problem = resolve('docs/guide.md#guide')
            self.assertEqual(problem, ArtefactProblem('cannot be read (read blocked)'),
                             'read failures cross the resolver boundary as a named problem')

    def test_heading_parser_failure_returns_a_named_problem(self) -> None:
        """Translate a heading parser failure before it reaches closure rules."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repository'
            (root / 'docs').mkdir(parents=True)
            (root / 'docs/guide.md').write_text('# Guide\n', encoding='utf-8')
            resolve = artefact_resolver(ValidationContext(root))
            with patch('docs_validation.roadmap_status.headings', side_effect=ValueError('bad Markdown')):
                problem = resolve('docs/guide.md#guide')
            self.assertEqual(problem, ArtefactProblem('cannot be parsed (bad Markdown)'),
                             'parser failures cross the resolver boundary as a named problem')

    def test_pf14_structural_component_targets_task_114(self):
        """Bind PF14's structural component to task 1.1.4 and the evidence-gate check."""
        obligations = ValidationContext(ROOT).load('spec/proof-obligations.json')['obligations']
        components = index_components(obligations)
        structural = [entry for entry in components['1.1.4'] if entry['id'] == 'PF14.structural@1.1.4']
        self.assertEqual(len(structural), 1, 'task 1.1.4 must have exactly one structural PF14 component')
        self.assertEqual((structural[0]['accepts'], structural[0]['evidence_source']),
                         (['tested'], 'checker:evidence-gate'), 'it accepts tested evidence from the gate check')


if __name__ == '__main__':
    unittest.main()
