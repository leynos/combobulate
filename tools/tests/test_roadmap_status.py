"""Prove roadmap ticks are backed by evidence (VO-4: MS-3, MS-4, and closure soundness)."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.roadmap_status import (
    ClosureInputs, check_roadmap_status, closure_failures, index_completions, index_components, task_closure,
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


def inputs(tasks: dict[str, dict], **overrides) -> ClosureInputs:
    """Build closure inputs in which every condition holds unless overridden."""
    values = {'tasks': tasks, 'completions': completions(tasks), 'decisions': {'D01': ACCEPTED},
              'components': {}, 'passed_checks': frozenset({'evidence-gate'}),
              'artefact_exists': lambda artefact: artefact == ARTEFACT}
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
        with self.assertRaisesRegex(AssertionError, message):
            task_closure(closure)

    def test_fully_supported_ticks_pass_on_chain_and_diamond(self):
        for name, shape in (('chain', chain()), ('diamond', diamond())):
            with self.subTest(shape=name):
                done = ticked(shape, *shape)
                self.assertEqual(task_closure(inputs(done))[0], list(shape), 'every supported tick is accepted')

    def test_tick_with_open_prerequisite_fails(self):
        for name, shape, target, missing in (('chain', chain(), '1.1.3', '1.1.2'),
                                             ('diamond', diamond(), '1.1.4', '1.1.3')):
            with self.subTest(shape=name):
                done = ticked(shape, *(task_id for task_id in shape if task_id != missing))
                self.assert_rejected(inputs(done), f'Task {target} is ticked but prerequisite {missing} is not ticked')

    def test_tick_citing_proposed_or_superseded_decision_fails(self):
        for lifecycle in ('proposed', 'superseded', 'withdrawn'):
            with self.subTest(lifecycle=lifecycle):
                closure = inputs(ticked(chain(), '1.1.1'), decisions={'D01': {'id': 'D01', 'lifecycle': lifecycle}})
                self.assert_rejected(closure, f'decision D01 is {lifecycle}, not accepted')

    def test_tick_without_completion_record_fails(self):
        closure = inputs(ticked(chain(), '1.1.1'), completions={})
        self.assert_rejected(closure, 'Task 1.1.1 is ticked but no completion record')

    def test_tick_with_unresolvable_artefact_fails(self):
        closure = inputs(ticked(chain(), '1.1.1'), artefact_exists=lambda artefact: False)
        self.assert_rejected(closure, f'artefact {ARTEFACT} does not resolve')

    def test_record_sourced_component_fails_closed(self):
        components = {'1.1.1': [component('PF14.proof@1.1.1', 'record', ['proof'])]}
        closure = inputs(ticked(chain(), '1.1.1'), components=components)
        self.assert_rejected(closure, 'component PF14.proof@1.1.1 has no admitted evidence record')

    def test_checker_component_needs_its_check_to_pass_in_this_run(self):
        components = {'1.1.1': [component('PF14.structural@1.1.1', 'checker:evidence-gate')]}
        self.assertEqual(task_closure(inputs(ticked(chain(), '1.1.1'), components=components))[0], ['1.1.1'],
                         'a passing evidence-gate check satisfies the structural component')
        closure = inputs(ticked(chain(), '1.1.1'), components=components, passed_checks=frozenset())
        self.assert_rejected(closure, 'component PF14.structural@1.1.1 needs check evidence-gate to pass')

    def test_supported_but_unticked_task_is_reported_not_failed(self):
        ticks, eligible = task_closure(inputs(ticked(chain(), '1.1.1')))
        self.assertEqual((ticks, eligible), (['1.1.1'], ['1.1.2']), 'only the next task becomes eligible')

    def test_closure_names_each_open_prerequisite(self):
        failures = closure_failures('1.1.2', inputs(ticked(chain(), '1.1.2')))
        self.assertIn('prerequisite 1.1.1 is not ticked', failures, 'closure soundness names the open prerequisite')


class ComponentsAndCompletions(unittest.TestCase):
    """MS-3 inputs are validated before closure reads them."""

    def obligation(self, *components: dict) -> dict:
        return {'id': 'PF14', 'tasks': ['1.1.4', '3.4.1'], 'components': list(components)}

    def test_every_obligation_task_needs_a_component(self):
        with self.assertRaisesRegex(AssertionError, 'PF14 has no component for tasks 3.4.1'):
            index_components([self.obligation(component('PF14.structural@1.1.4', 'checker:evidence-gate'))])

    def test_component_must_belong_to_its_obligation(self):
        with self.assertRaisesRegex(AssertionError, 'does not belong to PF14'):
            index_components([self.obligation(component('PF13.structural@1.1.4', 'checker:evidence-gate'))])

    def test_component_fields_must_agree_with_identity(self):
        broken = component('PF14.structural@1.1.4', 'checker:evidence-gate') | {'method': 'proof'}
        with self.assertRaisesRegex(AssertionError, 'disagrees with its method or task fields'):
            index_components([self.obligation(broken)])

    def test_component_cannot_accept_restricted(self):
        broken = component('PF14.structural@1.1.4', 'record', ['restricted'])
        with self.assertRaisesRegex(AssertionError, 'must accept a non-empty subset'):
            index_components([self.obligation(broken)])

    def test_checker_component_must_accept_tested(self):
        broken = component('PF14.structural@1.1.4', 'checker:evidence-gate', ['proof'])
        with self.assertRaisesRegex(AssertionError, 'must accept the tested level'):
            index_components([self.obligation(broken)])

    def test_completion_record_must_cite_known_decisions(self):
        with self.assertRaisesRegex(AssertionError, 'cites unknown decisions D99'):
            index_completions({'tasks': [{'task': '1.1.1', 'decisions': ['D99'], 'artefacts': [ARTEFACT]}]},
                              chain(), {'D01': ACCEPTED})


class RealRoadmap(unittest.TestCase):
    """The committed roadmap passes closure, and PF14.structural@1.1.4 is wired to the evidence gate."""

    def test_committed_roadmap_passes(self):
        check_roadmap_status(ValidationContext(ROOT))

    def test_pf14_structural_component_targets_task_114(self):
        obligations = ValidationContext(ROOT).load('spec/proof-obligations.json')['obligations']
        components = index_components(obligations)
        structural = [entry for entry in components['1.1.4'] if entry['id'] == 'PF14.structural@1.1.4']
        self.assertEqual(len(structural), 1, 'task 1.1.4 must have exactly one structural PF14 component')
        self.assertEqual((structural[0]['accepts'], structural[0]['evidence_source']),
                         (['tested'], 'checker:evidence-gate'), 'it accepts tested evidence from the gate check')


if __name__ == '__main__':
    unittest.main()
