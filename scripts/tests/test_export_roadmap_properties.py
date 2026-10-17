"""Exercise roadmap export invariants across generated structures."""
from __future__ import annotations

import copy
from pathlib import Path

from hypothesis import event, given, settings, strategies as st

from export_roadmap import parse_roadmap
from roadmap_render import render_document

ROOT = Path(__file__).resolve().parents[2]
ROADMAP = (ROOT / 'docs/roadmap.md').read_text(encoding='utf-8')
REQUIRED_CLASSES = {
    'multi-phase', 'single-phase', 'multi-step', 'single-step',
    'multi-task', 'single-task', 'no-details', 'has-details',
    'task-detail-count=0', 'task-detail-count=1', 'task-detail-count=2',
    'has-requires', 'no-requires', 'has-done', 'all-open',
}

WORDS = st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=8)
SENTENCE = st.lists(WORDS, min_size=1, max_size=12).map(lambda words: ' '.join(words).capitalize() + '.')
BETS = st.lists(st.sampled_from(['B01', 'B02', 'B03']), min_size=1, max_size=3, unique=True)
GOALS = st.lists(st.sampled_from(['G1', 'G2', 'G3']), min_size=1, max_size=3, unique=True)


def drawn_tasks(draw, phase_number: int, step_index: int, task_ids: list[str]) -> list[dict]:
    """Draw one step's tasks; e.g. its first task has no earlier dependency."""
    tasks = []
    task_count = draw(st.integers(1, 3))
    for task_index in range(1, task_count + 1):
        task_id = f'{phase_number}.{step_index}.{task_index}'
        requires = draw(st.lists(st.sampled_from(task_ids), max_size=2, unique=True)) if task_ids else []
        tasks.append({
            'id': task_id, 'title': draw(SENTENCE), 'requires': requires,
            'sections': f'§§{draw(st.integers(1, 19))}', 'success': draw(SENTENCE),
            'details': draw(st.lists(SENTENCE, max_size=2)), 'proof_first': draw(SENTENCE),
            'bets': draw(BETS), 'status': draw(st.sampled_from(['open', 'done'])),
        })
        task_ids.append(task_id)
    return tasks


def drawn_steps(draw, phase_number: int, task_ids: list[str]) -> list[dict]:
    """Draw one phase's steps; e.g. each task id uses the phase number."""
    steps = []
    step_count = draw(st.integers(1, 2))
    for step_index in range(1, step_count + 1):
        tasks = drawn_tasks(draw, phase_number, step_index, task_ids)
        steps.append({'number': f'{phase_number}.{step_index}', 'title': draw(SENTENCE).rstrip('.'),
                      'question': draw(SENTENCE), 'sections': f'§§{draw(st.integers(1, 19))}', 'tasks': tasks})
    return steps


@st.composite
def roadmaps(draw) -> dict:
    """Draw small, well-formed roadmaps; e.g. each phase has numbered steps."""
    phases: list[dict] = []
    task_ids: list[str] = []
    phase_count = draw(st.integers(1, 3))
    for phase_number in range(1, phase_count + 1):
        phases.append({'number': phase_number, 'title': draw(SENTENCE).rstrip('.'), 'idea': draw(SENTENCE),
                       'goals': draw(GOALS), 'gate': draw(SENTENCE), 'context': draw(SENTENCE),
                       'steps': drawn_steps(draw, phase_number, task_ids)})
    return {'revision': '0.2', 'phases': phases}


def count_classes(name: str, count: int) -> set[str]:
    """Label an observed count; e.g. one phase yields ``single-phase``."""
    cardinality = f'single-{name}' if count == 1 else f'multi-{name}'
    return {f'{name}-count={count}', cardinality}


def presence_class(condition: bool, present: str, absent: str) -> str:
    """Choose a feature label; e.g. true selects ``has-details``."""
    return present if condition else absent


def task_feature_classes(tasks: list[dict]) -> set[str]:
    """Label task features; e.g. no requirements yields ``no-requires``."""
    return {
        presence_class(any(task['requires'] for task in tasks), 'has-requires', 'no-requires'),
        presence_class(any(task['status'] == 'done' for task in tasks), 'has-done', 'all-open'),
    }


def structural_classes(structure: dict) -> set[str]:
    """Describe generated counts and classes for the property coverage gate."""
    phases = structure['phases']
    steps = [step for phase in phases for step in phase['steps']]
    tasks = [task for step in steps for task in step['tasks']]
    task_detail_counts = [len(task['details']) for task in tasks]
    detail_count = sum(task_detail_counts)
    classes = (
        count_classes('phase', len(phases))
        | count_classes('step', len(steps))
        | count_classes('task', len(tasks))
        | count_classes('detail', detail_count)
        | {
            presence_class(detail_count > 0, 'has-details', 'no-details'),
        }
        | task_feature_classes(tasks)
    )
    classes.update(f'task-detail-count={count}' for count in set(task_detail_counts))
    return classes


def test_render_then_export_round_trips():
    """Preserve generated roadmap structure through an independent render and parse path."""
    seen: set[str] = set()

    @settings(derandomize=True, max_examples=60, deadline=None)
    @given(roadmaps())
    def round_trip(structure: dict) -> None:
        """Check one generated structure and record the structural classes exercised."""
        classes = structural_classes(structure)
        for name in classes:
            event(name)
        seen.update(classes)
        exported = parse_roadmap(render_document(structure))
        expected = copy.deepcopy(structure)
        expected['status'] = exported['status']
        assert exported == expected, 'rendered roadmap must export to the drawn structure'

    round_trip()
    assert REQUIRED_CLASSES <= seen, f'generator never produced {sorted(REQUIRED_CLASSES - seen)}'
