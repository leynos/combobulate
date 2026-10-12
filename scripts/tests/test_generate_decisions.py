"""Prove the decision register renders every record and detects hand edits."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from generate_decisions import END, START, MarkerError, app, render, splice

ROOT = Path(__file__).resolve().parents[2]
REGISTER_PATH = ROOT / 'spec/decisions.json'
DOCUMENT_PATH = ROOT / 'docs/decision-register.md'
REGISTER = json.loads(REGISTER_PATH.read_text(encoding='utf-8'))


def accepted(register: dict, decision_id: str) -> dict:
    """Return a copy of the register with one decision accepted through a session answer."""
    edited = copy.deepcopy(register)
    record = next(entry for entry in edited['decisions'] if entry['id'] == decision_id)
    record.update({
        'lifecycle': 'accepted', 'decided_option': record['recommendation'], 'accepted_by': 'leynos',
        'accepted_on': '2026-10-10', 'adr': 'docs/adrs/adr-0003-initial-release-scope.md',
        'approval_reference': {'kind': 'session', 'url': 'https://example.org/session', 'author_login': 'leynos',
                               'names_decisions': [decision_id], 'answer': 'Accepted'},
    })
    return edited


def run_cli(*args: str) -> int:
    """Invoke the Cyclopts entry point and return its exit code."""
    with pytest.raises(SystemExit) as exited:
        app(list(args))
    return exited.value.code


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, Path]:
    """Copy the register and its document into an isolated directory."""
    register, document = tmp_path / 'decisions.json', tmp_path / 'decision-register.md'
    register.write_text(REGISTER_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    document.write_text(DOCUMENT_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    return register, document


def test_every_decision_and_candidate_is_rendered():
    text = render(REGISTER)
    for record in REGISTER['decisions']:
        assert f"### {record['id']}\n" in text, f"{record['id']} must have its own anchored heading"
    for candidate in REGISTER['candidate_adrs']:
        assert f"{candidate['id']}. {candidate['subject']}" in text, f"{candidate['id']} must be listed"


def test_deferred_dispositions_name_steps_and_tasks():
    text = ' '.join(render(REGISTER).split())
    assert 'Resource certification (technical-design.md §15): deferred to step 2.4 (B03)' in text, 'CA7 is a step'
    assert 'deferred to task 1.2.1' in text, 'three-part identifiers are tasks'


def test_rendering_is_deterministic():
    assert render(REGISTER) == render(copy.deepcopy(REGISTER)), 'rendering must not depend on identity'


def test_proposed_decision_renders_as_pending_with_its_recommendation():
    register = copy.deepcopy(REGISTER)
    record = next(entry for entry in register['decisions'] if entry['id'] == 'D03')
    record.update({'lifecycle': 'proposed', 'decided_option': None, 'accepted_by': None, 'accepted_on': None,
                   'approval_reference': None, 'adr': None})
    text = render(register)
    section = text[text.index('### D03\n'):text.index('### D04\n')]
    assert 'Decision: pending.' in section, 'a proposed record has no decision'
    assert '(recommended)' in section, 'the recommended option is marked'


def test_accepted_decision_renders_its_approval():
    section = render(accepted(REGISTER, 'D03'))
    section = ' '.join(section[section.index('### D03\n'):section.index('### D04\n')].split())
    assert 'Decision: option A, accepted on 2026-10-10 by `leynos`' in section, 'the outcome names its authority'
    assert '[session answer](https://example.org/session)' in section, 'the approval reference is linked'
    assert '[ADR-0003](adrs/adr-0003-initial-release-scope.md)' in section, 'the ADR is linked from docs/'


def test_splice_rejects_missing_or_repeated_markers():
    with pytest.raises(MarkerError, match='exactly one'):
        splice('# Register\n', 'body')
    with pytest.raises(MarkerError, match='exactly one'):
        splice(f'{START}\n{END}\n{START}\n{END}\n', 'body')


def test_committed_document_matches_the_register(workspace):
    register, document = workspace
    assert run_cli('--check', '--register', str(register), '--document', str(document)) == 0, 'no drift'


def test_check_tolerates_rewrapping(workspace):
    register, document = workspace
    text = document.read_text(encoding='utf-8')
    document.write_text(text.replace('Lifecycle: proposed.', 'Lifecycle:\nproposed.', 1), encoding='utf-8')
    assert run_cli('--check', '--register', str(register), '--document', str(document)) == 0, 'wrapping is free'


def test_check_reports_a_hand_edit(workspace, capsys):
    register, document = workspace
    text = document.read_text(encoding='utf-8')
    document.write_text(text.replace('Decision: pending.', 'Decision: option A.', 1), encoding='utf-8')
    assert run_cli('--check', '--register', str(register), '--document', str(document)) == 1, 'hand edits fail'
    assert 'scripts/generate_decisions.py' in capsys.readouterr().err, 'the failure names the generator'


def test_missing_markers_exit_two(workspace, capsys):
    register, document = workspace
    document.write_text('# Decision register\n', encoding='utf-8')
    assert run_cli('--register', str(register), '--document', str(document)) == 2, 'malformed documents exit 2'
    assert 'exactly one' in capsys.readouterr().err


def test_write_mode_regenerates_the_region(workspace):
    register, document = workspace
    document.write_text(f'# Decision register\n\n{START}\n\nstale\n\n{END}\n', encoding='utf-8')
    assert run_cli('--register', str(register), '--document', str(document)) == 0, 'writing succeeds'
    assert 'stale' not in document.read_text(encoding='utf-8'), 'the generated region is replaced'
    assert run_cli('--check', '--register', str(register), '--document', str(document)) == 0, 'writes are stable'


def test_check_reads_the_flag_from_the_environment(workspace, monkeypatch):
    register, document = workspace
    document.write_text(f'# Decision register\n\n{START}\n\nstale\n\n{END}\n', encoding='utf-8')
    monkeypatch.setenv('INPUT_CHECK', 'true')
    assert run_cli('--register', str(register), '--document', str(document)) == 1, 'INPUT_CHECK enables checking'
