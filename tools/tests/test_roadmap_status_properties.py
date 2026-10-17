"""Generate closure, component, and artefact cases beyond fixed examples."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.roadmap_status import (
    ArtefactProblem, ClosureInputs, artefact_resolver, component_failure, index_completions, task_closure,
)

GENERATED = settings(max_examples=60, derandomize=True, deadline=None)


@st.composite
def closure_states(draw):
    """Generate an ordered DAG with arbitrary tick states and complete evidence."""
    size = draw(st.integers(min_value=1, max_value=8))
    identifiers = [f'1.1.{index + 1}' for index in range(size)]
    prerequisites = {
        task_id: draw(st.lists(st.sampled_from(identifiers[:index]), unique=True, max_size=index))
        if index else []
        for index, task_id in enumerate(identifiers)
    }
    done = draw(st.lists(st.booleans(), min_size=size, max_size=size))
    tasks = {
        task_id: {
            'id': task_id,
            'requires': prerequisites[task_id],
            'status': 'done' if done[index] else 'open',
        }
        for index, task_id in enumerate(identifiers)
    }
    completions = {
        task_id: {'task': task_id, 'decisions': [], 'artefacts': ['docs/evidence.md']}
        for task_id in identifiers
    }
    return tasks, ClosureInputs(
        tasks=tasks,
        completions=completions,
        decisions={},
        components={},
        passed_checks=frozenset(),
        artefact_problem=lambda artefact: None if artefact == 'docs/evidence.md' else ArtefactProblem('is missing'),
    )


class RoadmapClosureProperties(unittest.TestCase):
    """Exercise dependency closure and evidence admission over generated inputs."""

    @GENERATED
    @given(state=closure_states())
    def test_tick_states_match_the_generated_prerequisite_graph(self, state):
        """Reject unsupported ticks and report exactly the eligible open tasks."""
        tasks, inputs = state
        missing_prerequisite = next((
            (task_id, required)
            for task_id, task in tasks.items() if task['status'] == 'done'
            for required in task['requires'] if tasks[required]['status'] != 'done'
        ), None)
        if missing_prerequisite is not None:
            with self.assertRaisesRegex(AssertionError, 'prerequisite .* is not ticked'):
                task_closure(inputs)
            return

        ticked, eligible = task_closure(inputs)
        expected_ticked = [task_id for task_id, task in tasks.items() if task['status'] == 'done']
        expected_eligible = [
            task_id for task_id, task in tasks.items()
            if task['status'] != 'done'
            and all(tasks[required]['status'] == 'done' for required in task['requires'])
        ]
        self.assertEqual(ticked, expected_ticked, 'all and only supported done tasks must be accepted')
        self.assertEqual(eligible, expected_eligible, 'eligibility must follow the generated prerequisites')

    @GENERATED
    @given(cited=st.lists(st.sampled_from(('D01', 'D02')), unique=True, max_size=2))
    def test_completion_accepts_any_set_of_known_decision_citations(self, cited):
        """Accept zero or more citations when every cited decision is known."""
        record = {'task': '1.1.1', 'decisions': cited, 'artefacts': ['docs/evidence.md']}
        tasks = {'1.1.1': {}}
        decisions = {'D01': {'lifecycle': 'accepted'}, 'D02': {'lifecycle': 'accepted'}}
        indexed = index_completions({'tasks': [record]}, tasks, decisions)
        self.assertEqual(indexed['1.1.1']['decisions'], cited,
                         'the record must preserve exactly its relevant decision citations')

    @GENERATED
    @given(unknown=st.lists(st.sampled_from(('D98', 'D99')), min_size=1, max_size=2, unique=True))
    def test_completion_rejects_each_generated_unknown_decision(self, unknown):
        """Reject generated citations that cannot resolve in the decision register."""
        record = {'task': '1.1.1', 'decisions': unknown, 'artefacts': ['docs/evidence.md']}
        with self.assertRaisesRegex(AssertionError, 'cites unknown decisions'):
            index_completions({'tasks': [record]}, {'1.1.1': {}}, {'D01': {'lifecycle': 'accepted'}})

    @GENERATED
    @given(check=st.from_regex(r'[a-z][a-z0-9-]{0,12}', fullmatch=True), passed=st.booleans())
    def test_checker_component_tracks_its_named_check(self, check, passed):
        """Satisfy generated checker components exactly when their named check passes."""
        component = {'id': 'PF01.test@1.1.1', 'evidence_source': f'checker:{check}', 'evidence': []}
        result = component_failure(component, frozenset({check}) if passed else frozenset())
        self.assertEqual(result is None, passed,
                         'checker-sourced evidence must follow the matching current-run check')

    @GENERATED
    @given(evidence=st.lists(st.text(max_size=20), max_size=5))
    def test_record_component_fails_closed_for_generated_evidence(self, evidence):
        """Keep arbitrary record payloads inadmissible until the evidence gate exists."""
        component = {'id': 'PF01.proof@1.1.1', 'evidence_source': 'record', 'evidence': evidence}
        result = component_failure(component, frozenset({'unrelated-check'}))
        self.assertIsNotNone(result, 'record evidence must remain fail-closed before EP-M5')

    @GENERATED
    @given(parts=st.lists(st.from_regex(r'[a-z][a-z0-9_-]{0,7}', fullmatch=True), min_size=1, max_size=4))
    def test_existing_nested_artefacts_resolve_inside_the_repository(self, parts):
        """Resolve generated nested paths when their existing files stay in-root."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repository'
            relative = Path(*parts[:-1], f'{parts[-1]}.md')
            target = root / relative
            target.parent.mkdir(parents=True)
            target.write_text('# Evidence\n', encoding='utf-8')
            resolve = artefact_resolver(ValidationContext(root))
            self.assertIsNone(resolve(relative.as_posix()), 'an existing descendant file must resolve')

    @GENERATED
    @given(depth=st.integers(min_value=1, max_value=4))
    def test_generated_parent_traversal_never_resolves_outside_the_repository(self, depth):
        """Reject generated parent traversals even when the escaped file exists."""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base.joinpath(*(['nested'] * depth))
            root.mkdir(parents=True)
            (base / 'outside.md').write_text('# Outside\n', encoding='utf-8')
            escaped = '/'.join(['..'] * depth + ['outside.md'])
            resolve = artefact_resolver(ValidationContext(root))
            problem = resolve(escaped)
            assert problem is not None, 'an escaped artefact must return a named problem'
            self.assertIn('outside the repository', problem.detail,
                          'an existing file outside the root must not resolve')


if __name__ == '__main__':
    unittest.main()
