"""Prove the canonical Markdown roadmap exports losslessly to its JSON view."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from export_roadmap import END, START, RoadmapStructureError, app, export_text, main, parse_roadmap

ROOT = Path(__file__).resolve().parents[2]
ROADMAP_PATH = ROOT / 'docs/roadmap.md'
EXPORT_PATH = ROOT / 'spec/roadmap.json'
ROADMAP = ROADMAP_PATH.read_text(encoding='utf-8')
ALL_OPEN_ROADMAP = (
    Path(__file__).parent / 'fixtures' / 'all_open_roadmap.txt'
).read_text(encoding='utf-8')
OPEN_TASK = '- [ ] 2.1.1. Implement'
REQUIRED_CLASSES = {
    'multi-phase', 'single-phase', 'multi-step', 'single-step',
    'multi-task', 'single-task', 'no-details', 'has-details',
    'task-detail-count=0', 'task-detail-count=1', 'task-detail-count=2',
    'has-requires', 'no-requires', 'has-done', 'all-open',
}


def committed_export() -> dict:
    """Load the committed JSON view that the drift check protects."""
    return json.loads(EXPORT_PATH.read_text(encoding='utf-8'))


def replace_once(text: str, old: str, new: str) -> str:
    """Edit one exact occurrence so each negative control changes one item."""
    assert text.count(old) == 1, f'expected exactly one occurrence of {old!r}'
    return text.replace(old, new)


def remove_first_task_bullet(text: str, label: str) -> str:
    """Remove one task field and its wrapped lines for a missing-field control."""
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(f'  - {label}'))
    end = next((index for index in range(start + 1, len(lines))
                if lines[index].startswith('  - ') or lines[index].startswith('- [')), len(lines))
    del lines[start:end]
    return '\n'.join(lines) + '\n'


def first_task(roadmap: dict) -> dict:
    """Return task 1.1.1, the target of the single-item drift controls."""
    return roadmap['phases'][0]['steps'][0]['tasks'][0]


def line_of(text: str, needle: str) -> int:
    """Return the 1-based line on which a needle starts."""
    return text[:text.index(needle)].count('\n') + 1


def test_export_matches_committed_json_view():
    """Keep every canonical Markdown field represented in the committed JSON view."""
    assert parse_roadmap(ROADMAP) == committed_export(), 'docs/roadmap.md must export exactly to spec/roadmap.json'


def test_serialized_export_is_byte_identical_and_deterministic():
    """Treat serialization details as part of the generated file contract."""
    committed = EXPORT_PATH.read_text(encoding='utf-8')
    assert export_text(ROADMAP) == committed, 'serialization must match the committed file'
    assert export_text(ROADMAP) == export_text(ROADMAP), 'export must be deterministic'


def test_export_is_independent_of_paragraph_wrapping():
    """Keep Markdown presentation changes from changing the parsed roadmap meaning."""
    rewrapped = replace_once(ROADMAP, 'Record the scope, decision authority, licence, and pre-1.0 API\n  policy.',
                             'Record the scope, decision authority, licence, and\n  pre-1.0 API policy.')
    assert parse_roadmap(rewrapped) == parse_roadmap(ROADMAP), 'wrapping must not change the export'


def test_open_checkboxes_export_as_open_status():
    """Keep open-checkbox assertions independent of the live roadmap state."""
    statuses = {task['status'] for phase in parse_roadmap(ALL_OPEN_ROADMAP)['phases']
                for step in phase['steps'] for task in step['tasks']}
    assert statuses == {'open'}, 'every task in the fixed fixture must export as open'


def test_checkboxes_export_as_task_status():
    """Require every completed JSON task to match a checked roadmap box."""
    ticked = set(re.findall(r'^- \[x\] (\d+\.\d+\.\d+)\.', ROADMAP, re.MULTILINE))
    exported = {task['id']: task['status'] for phase in parse_roadmap(ROADMAP)['phases']
                for step in phase['steps'] for task in step['tasks']}
    assert {task_id for task_id, status in exported.items() if status == 'done'} == ticked, (
        'exactly the ticked checkboxes export as done')
    assert set(exported.values()) <= {'open', 'done'}, 'status is open or done'


@pytest.mark.parametrize(('text', 'expected'), [
    pytest.param(ALL_OPEN_ROADMAP, 'proposed-all-tasks-open', id='all-open'),
    pytest.param(replace_once(ALL_OPEN_ROADMAP, '- [ ] 1.1.1. Record', '- [x] 1.1.1. Record'),
                 'tasks-in-progress', id='mixed'),
    pytest.param(ALL_OPEN_ROADMAP.replace('- [ ]', '- [x]'), 'all-tasks-done', id='all-done'),
])
def test_overall_status_matches_independent_expectations(text: str, expected: str):
    """Derive the aggregate status correctly for open, mixed, and completed task sets."""
    assert parse_roadmap(text)['status'] == expected, f'roadmap status must be {expected}'


def test_changed_title_changes_export():
    """Ensure a task title edit is visible in the derived JSON rather than ignored."""
    edited = replace_once(ROADMAP, '1.1.1. Record the scope', '1.1.1. Record only the scope')
    assert first_task(parse_roadmap(edited))['title'] != first_task(committed_export())['title'], (
        'a retitled task must drift from the committed export')


def test_changed_dependency_changes_export():
    """Keep dependency edits in canonical Markdown reflected by the JSON view."""
    edited = replace_once(ROADMAP, 'Requires 1.1.1, 1.1.2, 1.1.3.', 'Requires 1.1.1, 1.1.3.')
    task = parse_roadmap(edited)['phases'][0]['steps'][0]['tasks'][3]
    assert task['requires'] == ['1.1.1', '1.1.3'], 'the edited Requires line must be exported'


def test_ticked_checkbox_changes_status():
    """Make checkbox completion affect task status and aggregate roadmap status."""
    edited = replace_once(ALL_OPEN_ROADMAP, '- [ ] 1.1.1. Record', '- [x] 1.1.1. Record')
    assert first_task(parse_roadmap(edited))['status'] == 'done', 'a tick must export as done'


def test_missing_markers_are_rejected():
    """Reject a document that no longer identifies the canonical roadmap region."""
    with pytest.raises(RoadmapStructureError, match='exactly one'):
        parse_roadmap('# Roadmap\n')


def test_empty_marked_region_is_rejected():
    """Require at least one phase inside the marked canonical region."""
    text = f'Revision 0.2, 6 October 2026.\n\n{START}\n\n{END}\n'
    with pytest.raises(RoadmapStructureError, match='at least one phase'):
        parse_roadmap(text)


def test_phase_without_steps_is_rejected_at_its_heading():
    """Point to the phase heading when its body contains no numbered step."""
    text = (f'Revision 0.2, 6 October 2026.\n\n{START}\n\n'
            '## 1. Empty phase\n\nIdea: A phase without steps.\n\n'
            'Goals: G1 in `terms-of-reference.md` §6.\n\nContext.\n\nGate: Not ready.\n\n'
            f'{END}\n')
    with pytest.raises(RoadmapStructureError) as raised:
        parse_roadmap(text)
    assert raised.value.line == line_of(text, '## 1. Empty phase'), 'empty phase error must name its heading'


@pytest.mark.parametrize(('label', 'expected'), [
    ('See `technical-design.md`', 'technical-design reference'),
    ('Proof first:', 'proof-first'),
    ('Success:', 'success'),
])
def test_missing_required_task_bullet_is_rejected(label: str, expected: str):
    """Reject incomplete task contracts and name the absent required field."""
    edited = remove_first_task_bullet(ROADMAP, label)
    with pytest.raises(RoadmapStructureError) as raised:
        parse_roadmap(edited)
    assert raised.value.line == line_of(edited, '- [x] 1.1.1.'), 'missing task detail must name its task'
    assert expected in str(raised.value), f'error must identify missing {expected}'


@pytest.mark.parametrize(('duplicate_bullet', 'field'), [
    ('  - Requires 1.1.2.', 'requires'),
    ('  - See `technical-design.md` `1.', 'sections'),
    ('  - Proof first: Duplicate proof. Bets: B01.', 'proof_first'),
    ('  - Success: Duplicate criterion.', 'success'),
])
def test_duplicate_task_fields_are_rejected(duplicate_bullet: str, field: str):
    """Reject duplicate task fields instead of silently overriding their values."""
    edited = replace_once(ROADMAP, '- [ ] 1.1.3.', f'{duplicate_bullet}\n- [ ] 1.1.3.')
    with pytest.raises(RoadmapStructureError) as raised:
        parse_roadmap(edited)
    assert raised.value.line == line_of(edited, duplicate_bullet.strip()), 'duplicate error must name its bullet'
    assert f'duplicate task {field} bullet' in str(raised.value), 'error must identify the duplicate task field'


@pytest.mark.parametrize(('replacement', 'message'), [
    ('  - Proof first: Bets: B01.', 'proof-first bullet must end with its bets'),
    ('  - Proof first: State a property. Bets: .', 'proof-first bullet must include at least one bet'),
])
def test_incomplete_proof_first_bullet_is_rejected(replacement: str, message: str):
    """Reject proof-first fields without a statement or a linked bet."""
    original = ('  - Proof first: Write decision and exception authority before accepting claims;\n'
                '    approval is not verification. Bets: B01.')
    edited = replace_once(ROADMAP, original, replacement)
    with pytest.raises(RoadmapStructureError, match=message):
        parse_roadmap(edited)


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
    """Keep each unsupported structure error attached to its source line."""
    with pytest.raises(RoadmapStructureError) as raised:
        parse_roadmap(text)
    assert raised.value.line == line, f'error must name line {line}: {raised.value}'


@pytest.mark.parametrize(('replacement', 'source_node'), [
    pytest.param('```text\nnot a paragraph\n```', '```text', id='code-block'),
    pytest.param('---', '---', id='thematic-break'),
])
def test_phase_rejects_nonparagraph_body_with_line_and_cli_exit_two(
        replacement: str, source_node: str, workspace, capsys):
    """Reject unsupported phase-body nodes consistently in the parser and command line."""
    context = ('This phase permits foundational work, but its output must include a runnable\n'
               'public path. Document preparation alone does not complete a task.')
    edited = replace_once(ROADMAP, context, replacement)
    expected_line = line_of(edited, source_node)
    with pytest.raises(RoadmapStructureError) as raised:
        parse_roadmap(edited)
    assert raised.value.line == expected_line, f'non-paragraph phase node must name line {expected_line}'

    roadmap, export = workspace
    roadmap.write_text(edited, encoding='utf-8')
    assert run_cli('--check', '--roadmap', str(roadmap), '--export', str(export)) == 2, (
        'non-paragraph phase nodes must exit as malformed input')
    assert f':{expected_line}:' in capsys.readouterr().err, 'CLI error must include the malformed node line'


def test_goals_reference_rejects_unrecognized_trailing_text():
    """Prevent trailing Goals text from disappearing during structural export."""
    edited = replace_once(ROADMAP,
                          'Goals: G1, G2, G6, G7, G8 in `terms-of-reference.md` §6.',
                          'Goals: G1, G2, G6, G7, G8 in `terms-of-reference.md` §6. Additional acceptance rule.')
    expected_line = line_of(edited, 'Goals: G1, G2, G6, G7, G8')
    with pytest.raises(RoadmapStructureError) as raised:
        parse_roadmap(edited)
    assert raised.value.line == expected_line, f'unknown goal suffix must name line {expected_line}'
    assert 'must end with' in str(raised.value), 'error must identify the incomplete Goals grammar'


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
    """Let check mode succeed when the committed export matches its canonical source."""
    roadmap, export = workspace
    assert run_cli('--check', '--roadmap', str(roadmap), '--export', str(export)) == 0, 'matching export passes'
    assert 'matches' in capsys.readouterr().out, 'matching export must report that it matches'


def test_cli_check_reports_drift_with_a_diff(workspace, capsys):
    """Show actionable serialized differences and exit one when check mode detects drift."""
    roadmap, export = workspace
    roadmap.write_text(replace_once(ROADMAP, '1.1.1. Record the scope', '1.1.1. Record only the scope'),
                       encoding='utf-8')
    assert run_cli('--check', '--roadmap', str(roadmap), '--export', str(export)) == 1, 'drift must exit 1'
    captured = capsys.readouterr()
    assert '+' in captured.out and 'Record only the scope' in captured.out, 'the diff must show the change'
    assert 'stale' in captured.err, 'drift diagnostic must identify the export as stale'


def test_cli_reports_malformed_structure_with_exit_two(workspace, capsys):
    """Reserve exit two for malformed input and include its source line in diagnostics."""
    roadmap, export = workspace
    roadmap.write_text(replace_once(ROADMAP, OPEN_TASK, OPEN_TASK.replace('[ ] ', '')), encoding='utf-8')
    assert run_cli('--check', '--roadmap', str(roadmap), '--export', str(export)) == 2, 'malformed input exits 2'
    expected_line = line_of(ROADMAP, OPEN_TASK)
    assert f':{expected_line}:' in capsys.readouterr().err, (
        f'malformed-task diagnostic must include source line {expected_line}')


def test_cli_reads_check_flag_from_environment(workspace, monkeypatch):
    """Honor INPUT_CHECK when the command line does not explicitly select check mode."""
    roadmap, export = workspace
    export.write_text('{}\n', encoding='utf-8')
    monkeypatch.setenv('INPUT_CHECK', 'true')
    assert run_cli('--roadmap', str(roadmap), '--export', str(export)) == 1, 'INPUT_CHECK must enable checking'


def test_write_mode_refreshes_the_export(workspace):
    """Rewrite the derived file from canonical Markdown when write mode is selected."""
    roadmap, export = workspace
    export.write_text('{}\n', encoding='utf-8')
    assert main(roadmap=roadmap, export=export) == 0, 'writing succeeds'
    assert export.read_text(encoding='utf-8') == EXPORT_PATH.read_text(encoding='utf-8'), 'export is rewritten'
