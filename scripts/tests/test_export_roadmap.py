"""Prove the canonical Markdown roadmap exports losslessly to its JSON view."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest
from hypothesis import event, given, settings, strategies as st

from export_roadmap import END, START, RoadmapStructureError, app, export_text, main, parse_roadmap
from roadmap_render import render_document

ROOT = Path(__file__).resolve().parents[2]
ROADMAP_PATH = ROOT / 'docs/roadmap.md'
EXPORT_PATH = ROOT / 'spec/roadmap.json'
ROADMAP = ROADMAP_PATH.read_text(encoding='utf-8')
OPEN_TASK = '- [ ] 2.1.1. Implement'
REQUIRED_CLASSES = {'multi-phase', 'single-phase', 'has-details', 'no-details', 'has-requires', 'has-done',
                    'all-open'}


def committed_export() -> dict:
    """Load the committed JSON view that the drift check protects."""
    return json.loads(EXPORT_PATH.read_text(encoding='utf-8'))


def replace_once(text: str, old: str, new: str) -> str:
    """Edit one exact occurrence so each negative control changes one item."""
    assert text.count(old) == 1, f'expected exactly one occurrence of {old!r}'
    return text.replace(old, new)


def first_task(roadmap: dict) -> dict:
    """Return task 1.1.1, the target of the single-item drift controls."""
    return roadmap['phases'][0]['steps'][0]['tasks'][0]


def line_of(text: str, needle: str) -> int:
    """Return the 1-based line on which a needle starts."""
    return text[:text.index(needle)].count('\n') + 1


def test_export_matches_committed_json_view():
    assert parse_roadmap(ROADMAP) == committed_export(), 'docs/roadmap.md must export exactly to spec/roadmap.json'


def test_serialized_export_is_byte_identical_and_deterministic():
    committed = EXPORT_PATH.read_text(encoding='utf-8')
    assert export_text(ROADMAP) == committed, 'serialization must match the committed file'
    assert export_text(ROADMAP) == export_text(ROADMAP), 'export must be deterministic'


def test_export_is_independent_of_paragraph_wrapping():
    rewrapped = replace_once(ROADMAP, 'Record the scope, decision authority, licence, and pre-1.0 API\n  policy.',
                             'Record the scope, decision authority, licence, and\n  pre-1.0 API policy.')
    assert parse_roadmap(rewrapped) == parse_roadmap(ROADMAP), 'wrapping must not change the export'


def test_checkboxes_export_as_task_status():
    ticked = set(re.findall(r'^- \[x\] (\d+\.\d+\.\d+)\.', ROADMAP, re.MULTILINE))
    exported = {task['id']: task['status'] for phase in parse_roadmap(ROADMAP)['phases']
                for step in phase['steps'] for task in step['tasks']}
    assert {task_id for task_id, status in exported.items() if status == 'done'} == ticked, (
        'exactly the ticked checkboxes export as done')
    assert set(exported.values()) <= {'open', 'done'}, 'status is open or done'


def test_changed_title_changes_export():
    edited = replace_once(ROADMAP, '1.1.1. Record the scope', '1.1.1. Record only the scope')
    assert first_task(parse_roadmap(edited))['title'] != first_task(committed_export())['title'], (
        'a retitled task must drift from the committed export')


def test_changed_dependency_changes_export():
    edited = replace_once(ROADMAP, 'Requires 1.1.1, 1.1.2, 1.1.3.', 'Requires 1.1.1, 1.1.3.')
    task = parse_roadmap(edited)['phases'][0]['steps'][0]['tasks'][3]
    assert task['requires'] == ['1.1.1', '1.1.3'], 'the edited Requires line must be exported'


def test_ticked_checkbox_changes_status():
    edited = replace_once(ROADMAP, OPEN_TASK, OPEN_TASK.replace('[ ]', '[x]'))
    task = parse_roadmap(edited)['phases'][1]['steps'][0]['tasks'][0]
    assert (task['id'], task['status']) == ('2.1.1', 'done'), 'a tick must export as done'


def test_missing_markers_are_rejected():
    with pytest.raises(RoadmapStructureError, match='exactly one'):
        parse_roadmap('# Roadmap\n')


@pytest.mark.parametrize(('text', 'line'), [
    pytest.param(f'Revision 0.2, 6 October 2026.\n\n{START}\n\n#### 1. Too deep\n\n{END}\n', 5, id='heading-level'),
    pytest.param(replace_once(ROADMAP, OPEN_TASK, OPEN_TASK.replace('[ ] ', '')),
                 line_of(ROADMAP, OPEN_TASK), id='task-without-checkbox'),
    pytest.param(replace_once(ROADMAP, '  - Requires 1.1.1, 1.1.2, 1.1.3.', '  - Mystery note.'),
                 line_of(ROADMAP, '  - Requires 1.1.1, 1.1.2, 1.1.3.'), id='unlabelled-bullet'),
    pytest.param(replace_once(ROADMAP, '  - Requires 1.1.1, 1.1.2, 1.1.3.', '  - [x] A ticked detail.'),
                 line_of(ROADMAP, '  - Requires 1.1.1, 1.1.2, 1.1.3.'), id='ticked-detail'),
])
def test_malformed_structure_names_its_line(text: str, line: int):
    with pytest.raises(RoadmapStructureError) as raised:
        parse_roadmap(text)
    assert raised.value.line == line, f'error must name line {line}: {raised.value}'


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, Path]:
    """Copy the roadmap and its export into an isolated directory."""
    roadmap, export = tmp_path / 'roadmap.md', tmp_path / 'roadmap.json'
    roadmap.write_text(ROADMAP, encoding='utf-8')
    export.write_text(EXPORT_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    return roadmap, export


def run_cli(*args: str) -> int:
    """Invoke the Cyclopts entry point and return its exit code."""
    with pytest.raises(SystemExit) as exited:
        app(list(args))
    return exited.value.code


def test_cli_check_passes_on_matching_export(workspace, capsys):
    roadmap, export = workspace
    assert run_cli('--check', '--roadmap', str(roadmap), '--export', str(export)) == 0, 'matching export passes'
    assert 'matches' in capsys.readouterr().out


def test_cli_check_reports_drift_with_a_diff(workspace, capsys):
    roadmap, export = workspace
    roadmap.write_text(replace_once(ROADMAP, '1.1.1. Record the scope', '1.1.1. Record only the scope'),
                       encoding='utf-8')
    assert run_cli('--check', '--roadmap', str(roadmap), '--export', str(export)) == 1, 'drift must exit 1'
    captured = capsys.readouterr()
    assert '+' in captured.out and 'Record only the scope' in captured.out, 'the diff must show the change'
    assert 'stale' in captured.err


def test_cli_reports_malformed_structure_with_exit_two(workspace, capsys):
    roadmap, export = workspace
    roadmap.write_text(replace_once(ROADMAP, OPEN_TASK, OPEN_TASK.replace('[ ] ', '')), encoding='utf-8')
    assert run_cli('--check', '--roadmap', str(roadmap), '--export', str(export)) == 2, 'malformed input exits 2'
    assert f':{line_of(ROADMAP, OPEN_TASK)}:' in capsys.readouterr().err


def test_cli_reads_check_flag_from_environment(workspace, monkeypatch):
    roadmap, export = workspace
    export.write_text('{}\n', encoding='utf-8')
    monkeypatch.setenv('INPUT_CHECK', 'true')
    assert run_cli('--roadmap', str(roadmap), '--export', str(export)) == 1, 'INPUT_CHECK must enable checking'


def test_write_mode_refreshes_the_export(workspace):
    roadmap, export = workspace
    export.write_text('{}\n', encoding='utf-8')
    assert main(roadmap=roadmap, export=export) == 0, 'writing succeeds'
    assert export.read_text(encoding='utf-8') == EXPORT_PATH.read_text(encoding='utf-8'), 'export is rewritten'


WORDS = st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=8)
SENTENCE = st.lists(WORDS, min_size=1, max_size=12).map(lambda words: ' '.join(words).capitalize() + '.')
BETS = st.lists(st.sampled_from(['B01', 'B02', 'B03']), min_size=1, max_size=3, unique=True)
GOALS = st.lists(st.sampled_from(['G1', 'G2', 'G3']), min_size=1, max_size=3, unique=True)


@st.composite
def roadmaps(draw) -> dict:
    """Draw small, well-formed roadmap structures in canonical numbering."""
    phases: list[dict] = []
    task_ids: list[str] = []
    for phase_number in range(1, draw(st.integers(1, 3)) + 1):
        steps = []
        for step_index in range(1, draw(st.integers(1, 2)) + 1):
            tasks = []
            for task_index in range(1, draw(st.integers(1, 3)) + 1):
                task_id = f'{phase_number}.{step_index}.{task_index}'
                requires = draw(st.lists(st.sampled_from(task_ids), max_size=2, unique=True)) if task_ids else []
                tasks.append({
                    'id': task_id, 'title': draw(SENTENCE), 'requires': requires,
                    'sections': f'§§{draw(st.integers(1, 19))}', 'success': draw(SENTENCE),
                    'details': draw(st.lists(SENTENCE, max_size=2)), 'proof_first': draw(SENTENCE),
                    'bets': draw(BETS), 'status': draw(st.sampled_from(['open', 'done'])),
                })
                task_ids.append(task_id)
            steps.append({'number': f'{phase_number}.{step_index}', 'title': draw(SENTENCE).rstrip('.'),
                          'question': draw(SENTENCE), 'sections': f'§§{draw(st.integers(1, 19))}', 'tasks': tasks})
        phases.append({'number': phase_number, 'title': draw(SENTENCE).rstrip('.'), 'idea': draw(SENTENCE),
                       'goals': draw(GOALS), 'gate': draw(SENTENCE), 'context': draw(SENTENCE), 'steps': steps})
    return {'revision': '0.2', 'phases': phases}


def structural_classes(structure: dict) -> set[str]:
    """Classify a drawn roadmap so the property can prove its generator's reach."""
    tasks = [task for phase in structure['phases'] for step in phase['steps'] for task in step['tasks']]
    return {
        'multi-phase' if len(structure['phases']) > 1 else 'single-phase',
        'has-details' if any(task['details'] for task in tasks) else 'no-details',
        'has-requires' if any(task['requires'] for task in tasks) else 'no-requires',
        'has-done' if any(task['status'] == 'done' for task in tasks) else 'all-open',
    }


def test_render_then_export_round_trips():
    seen: set[str] = set()

    @settings(derandomize=True, max_examples=60, deadline=None)
    @given(roadmaps())
    def round_trip(structure: dict) -> None:
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
