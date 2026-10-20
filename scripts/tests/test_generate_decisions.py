"""Prove the decision register renders every record and detects hand edits."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from hypothesis import example, given, strategies as st

from generate_decisions import (
    END, START, MarkerError, app, quoted_answer, region_headings, region_words, render, splice,
)

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
    """Render an anchored section for every decision and candidate ADR."""
    text = render(REGISTER)
    for record in REGISTER['decisions']:
        assert f"### {record['id']}\n" in text, f"{record['id']} must have its own anchored heading"
    for candidate in REGISTER['candidate_adrs']:
        assert f"{candidate['id']}. {candidate['subject']}" in text, f"{candidate['id']} must be listed"


def test_deferred_dispositions_name_steps_and_tasks():
    """Preserve the distinction between deferred roadmap steps and tasks."""
    text = ' '.join(render(REGISTER).split())
    assert 'Resource certification (technical-design.md §15): deferred to step 2.4 (B03)' in text, 'CA7 is a step'
    assert 'deferred to task 1.2.1' in text, 'three-part identifiers are tasks'


def test_rendering_is_deterministic():
    """Render equivalent register data identically, regardless of object identity."""
    assert render(REGISTER) == render(copy.deepcopy(REGISTER)), 'rendering must not depend on identity'


def test_proposed_decision_renders_as_pending_with_its_recommendation():
    """Keep recommendations visible without presenting proposals as accepted."""
    register = copy.deepcopy(REGISTER)
    record = next(entry for entry in register['decisions'] if entry['id'] == 'D03')
    record.update({'lifecycle': 'proposed', 'decided_option': None, 'accepted_by': None, 'accepted_on': None,
                   'approval_reference': None, 'adr': None})
    text = render(register)
    section = text[text.index('### D03\n'):text.index('### D04\n')]
    assert 'Decision: pending.' in section, 'a proposed record has no decision'
    assert '(recommended)' in section, 'the recommended option is marked'


def test_accepted_decision_renders_its_approval():
    """Render the accepted option together with its approval and ADR links."""
    section = render(accepted(REGISTER, 'D03'))
    section = ' '.join(section[section.index('### D03\n'):section.index('### D04\n')].split())
    assert 'Decision: option A, accepted on 2026-10-10 by `leynos`' in section, 'the outcome names its authority'
    assert '[session answer](https://example.org/session)' in section, 'the approval reference is linked'
    assert '[ADR-0003](adrs/adr-0003-initial-release-scope.md)' in section, 'the ADR is linked from docs/'


def test_multi_paragraph_answer_keeps_its_paragraph_break():
    """Keep separate sponsor-answer paragraphs in the rendered block quote."""
    text = render(REGISTER)
    section = text[text.index('### D07\n'):text.index('### D08\n')]
    assert 'Answer, quoted verbatim:' in section, 'the session answer is quoted'
    assert '\n>\n> This breaks from current DF12 standards' in section, 'the blank line in the answer is kept'


def test_answer_soft_line_break_keeps_words_in_one_paragraph():
    """Preserve all answer words while reflowing a soft line break."""
    register = accepted(REGISTER, 'D03')
    record = next(entry for entry in register['decisions'] if entry['id'] == 'D03')
    record['approval_reference']['answer'] = 'First line.\nSecond line.'
    text = render(register)
    section = text[text.index('### D03\n'):text.index('### D04\n')]
    assert '> First line. Second line.\n' in section, 'a soft break may reflow without changing the quoted words'
    assert record['approval_reference']['answer'] == 'First line.\nSecond line.', 'the approval answer stays intact'


@example(paragraphs=[['single']], separator=' ')
@example(paragraphs=[['x' * 140], [], ['éЖ字']], separator='\n')
@given(
    paragraphs=st.lists(st.lists(st.text(alphabet='abcXYZ09-_/.,!?éЖ字', min_size=1, max_size=140),
                                 max_size=5), min_size=2, max_size=5),
    separator=st.sampled_from((' ', '\n', '  \n ')),
)
def test_quoted_answer_preserves_generated_words_and_paragraphs(paragraphs, separator):
    """Preserve generated words, empty paragraphs, and long tokens through quote reflow."""
    answer = '\n\n'.join(separator.join(words) for words in paragraphs)
    record = {'approval_reference': {'answer': answer}}
    rendered = quoted_answer(record)
    heading, ending = 'Answer, quoted verbatim:\n\n', '\n\n'

    assert rendered.startswith(heading) and rendered.endswith(ending), 'the quote must retain its framing'
    quoted = rendered[len(heading):-len(ending)]
    restored = []
    for paragraph in quoted.split('\n>\n'):
        lines = paragraph.splitlines()
        assert all(line.startswith('> ') for line in lines), 'every content line must remain in the quote'
        restored.append(' '.join(line[2:] for line in lines).split())
    assert restored == paragraphs, 'reflow must preserve every word and each paragraph, including empty ones'
    assert record['approval_reference']['answer'] == answer, 'rendering must preserve the original answer'


def test_splice_rejects_missing_or_repeated_markers():
    """Reject generated regions without exactly one marker pair."""
    with pytest.raises(MarkerError, match='exactly one'):
        splice('# Register\n', 'body')
    with pytest.raises(MarkerError, match='exactly one'):
        splice(f'{START}\n{END}\n{START}\n{END}\n', 'body')


def test_committed_document_matches_the_register(workspace):
    """The checked-in decision register matches the rendered source register."""
    register, document = workspace
    assert run_cli('--check', '--register', str(register), '--document', str(document)) == 0, 'no drift'


def test_check_tolerates_rewrapping(workspace):
    """Allow harmless Markdown line wrapping in the generated decision region."""
    register, document = workspace
    text = document.read_text(encoding='utf-8')
    document.write_text(text.replace('Lifecycle: proposed.', 'Lifecycle:\nproposed.', 1), encoding='utf-8')
    assert run_cli('--check', '--register', str(register), '--document', str(document)) == 0, 'wrapping is free'


def test_check_rejects_a_heading_absorbed_into_paragraph_text(workspace):
    """Detect a lost section anchor even when the generated words are unchanged."""
    register, document = workspace
    original = document.read_text(encoding='utf-8')
    edited = original.replace('\n\n### D03\n\n', ' ### D03\n\n', 1)
    assert region_words(edited) == region_words(original), 'the mutation must preserve the word sequence'
    assert region_headings(edited) != region_headings(original), 'the mutation must remove a heading anchor'
    document.write_text(edited, encoding='utf-8')
    assert run_cli('--check', '--register', str(register), '--document', str(document)) == 1, 'heading drift fails'


def test_check_reports_a_hand_edit(workspace, capsys):
    """Fail check-only generation when the committed register has been edited."""
    register, document = workspace
    text = document.read_text(encoding='utf-8')
    edited = text.replace('Subject: ', 'Subject: Hand-edited ', 1)
    assert edited != text, 'the control must actually edit the generated region'
    document.write_text(edited, encoding='utf-8')
    assert run_cli('--check', '--register', str(register), '--document', str(document)) == 1, 'hand edits fail'
    assert 'scripts/generate_decisions.py' in capsys.readouterr().err, 'the failure names the generator'


def test_missing_markers_exit_two(workspace, capsys):
    """Report malformed marker structure with the CLI's usage-error status."""
    register, document = workspace
    document.write_text('# Decision register\n', encoding='utf-8')
    assert run_cli('--register', str(register), '--document', str(document)) == 2, 'malformed documents exit 2'
    assert 'exactly one' in capsys.readouterr().err


def test_write_mode_regenerates_the_region(workspace):
    """Replace stale generated content and leave a stable checkable document."""
    register, document = workspace
    document.write_text(f'# Decision register\n\n{START}\n\nstale\n\n{END}\n', encoding='utf-8')
    assert run_cli('--register', str(register), '--document', str(document)) == 0, 'writing succeeds'
    assert 'stale' not in document.read_text(encoding='utf-8'), 'the generated region is replaced'
    assert run_cli('--check', '--register', str(register), '--document', str(document)) == 0, 'writes are stable'


def test_check_reads_the_flag_from_the_environment(workspace, monkeypatch):
    """Honor the action input that enables check mode without a CLI flag."""
    register, document = workspace
    document.write_text(f'# Decision register\n\n{START}\n\nstale\n\n{END}\n', encoding='utf-8')
    monkeypatch.setenv('INPUT_CHECK', 'true')
    assert run_cli('--register', str(register), '--document', str(document)) == 1, 'INPUT_CHECK enables checking'
