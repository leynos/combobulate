#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["cyclopts==5.2.0"]
# ///
"""Render `docs/decision-register.md` from its master, `spec/decisions.json`.

The register records each decision that controls acceptance: the questions it
answers, the authority that may accept it, the options considered, the
recommendation, and, once accepted, the chosen option with its approval
reference and ADR. The generated region lies between the decisions markers;
prose outside the markers is maintained by hand.

Run ``scripts/generate_decisions.py`` after editing the register to rewrite
the region, or ``scripts/generate_decisions.py --check`` (``INPUT_CHECK=true``
in CI) to fail when the document has drifted. The check ignores line wrapping,
because the Markdown formatter rewraps generated paragraphs. Exit codes: 0 when
the region is written or matches, 1 on drift, and 2 when the document lacks
exactly one marker pair. The design checker imports `render`, `START`, and
`END` from this file for its own semantic drift check.
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import cyclopts
from cyclopts import App

ROOT = Path(__file__).resolve().parents[1]

START = '<!-- decisions:start -->'
END = '<!-- decisions:end -->'
ROLE_NAMES = {'sponsor': 'sponsor', 'technical-owner': 'technical owner'}
APPROVAL_NAMES = {'session': 'session answer', 'pr-review': 'pull request review',
                  'pr-comment': 'pull request comment', 'commit': 'commit'}


class MarkerError(ValueError):
    """Report a document without exactly one marker pair; e.g. a missing end marker."""


def paragraph(text: str) -> str:
    """Wrap one paragraph at 80 columns; e.g. paragraph('Subject: x') ends with a blank line."""
    return textwrap.fill(text, 80, break_long_words=False, break_on_hyphens=False) + '\n\n'


def bullet(text: str) -> str:
    """Wrap one list item with a hanging indent; e.g. bullet('A. Option') starts with '- '."""
    return textwrap.fill(text, 80, initial_indent='- ', subsequent_indent='  ', break_long_words=False,
                         break_on_hyphens=False) + '\n'


def adr_link(path: str) -> str:
    """Link an ADR path from `docs/`; e.g. 'docs/adrs/adr-0002-x.md' becomes '[ADR-0002](adrs/...)'."""
    relative = path.removeprefix('docs/')
    number = relative.removeprefix('adrs/adr-')[:4]
    return f'[ADR-{number}]({relative})'


def outcome(record: dict) -> str:
    """Describe a record's decision; a proposed record is pending, an accepted one names its approval."""
    if record['lifecycle'] in {'proposed', 'withdrawn'}:
        return 'Decision: pending.' if record['lifecycle'] == 'proposed' else 'Decision: withdrawn.'
    reference = record['approval_reference']
    approval = f"[{APPROVAL_NAMES[reference['kind']]}]({reference['url']})"
    text = (f"Decision: option {record['decided_option']}, accepted on {record['accepted_on']} by "
            f"`{record['accepted_by']}` ({approval}).")
    return text


def quoted_answer(record: dict) -> str:
    """Quote a session answer verbatim as a blockquote, keeping its paragraph breaks."""
    reference = record['approval_reference']
    if reference is None or 'answer' not in reference:
        return ''
    paragraphs = [textwrap.fill(part, 78, initial_indent='> ', subsequent_indent='> ', break_long_words=False,
                                break_on_hyphens=False) for part in reference['answer'].split('\n\n')]
    return 'Answer, quoted verbatim:\n\n' + '\n>\n'.join(paragraphs) + '\n\n'


def lineage(record: dict) -> str:
    """Describe supersession links; an unlinked record renders nothing."""
    parts = []
    if record['supersedes']:
        parts.append('Supersedes: ' + ', '.join(f'[{other}](#{other.lower()})' for other in record['supersedes']) + '.')
    if record['superseded_by']:
        other = record['superseded_by']
        parts.append(f'Superseded by: [{other}](#{other.lower()}).')
    return paragraph(' '.join(parts)) if parts else ''


def render_decision(record: dict) -> str:
    """Render one decision with its own `### Dnn` heading, so its anchor is `#dnn`."""
    questions = ', '.join(record['questions']) or 'none'
    roles = ', '.join(ROLE_NAMES[role] for role in record['authority_roles'])
    options = ''.join(
        bullet(f"{option['id']}. {option['summary']}"
               + (' (recommended)' if option['id'] == record['recommendation'] else ''))
        for option in record['options']
    )
    adr = adr_link(record['adr']) if record['adr'] else 'none yet'
    return ''.join([
        f"### {record['id']}\n\n",
        paragraph(f"Subject: {record['subject']}."),
        paragraph(f'Terms-of-reference questions: {questions}. Authority: {roles}.'),
        paragraph(f"Lifecycle: {record['lifecycle']}."),
        'Options:\n\n', options, '\n',
        paragraph(f"Recommendation rationale: {record['rationale']}"),
        paragraph(outcome(record)),
        quoted_answer(record),
        lineage(record),
        paragraph(f'ADR: {adr}.'),
    ])


def roadmap_item(identifier: str) -> str:
    """Name a roadmap item by its depth; e.g. '2.4' is a step and '1.2.1' is a task."""
    return f"{'task' if identifier.count('.') == 2 else 'step'} {identifier}"


def render_candidate(candidate: dict) -> str:
    """Render one candidate ADR subject with its disposition."""
    disposition = candidate['disposition']
    if disposition['kind'] == 'adr':
        target = 'recorded in ' + ' and '.join(disposition['adrs'])
    else:
        target = f"deferred to {roadmap_item(disposition['roadmap_item'])}"
        if 'bet' in disposition:
            target += f" ({disposition['bet']})"
    return bullet(f"{candidate['id']}. {candidate['subject']} ({candidate['source']}): {target}; disposition "
                  f"decided by [{candidate['decision']}](#{candidate['decision'].lower()}).")


def render(register: dict) -> str:
    """Render the generated region body from the register master."""
    output = ['## Decisions\n\n']
    output.extend(render_decision(record) for record in register['decisions'])
    output.append('## Candidate ADR subjects\n\n')
    output.extend(render_candidate(candidate) for candidate in register['candidate_adrs'])
    return ''.join(output).rstrip()


def splice(text: str, body: str) -> str:
    """Replace the generated region; e.g. splice(document, render(register))."""
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        raise MarkerError(f'The document must contain exactly one {START} ... {END} pair.')
    before, rest = text.split(START)
    _, after = rest.split(END)
    return before + START + '\n\n' + body + '\n\n' + END + after


def region_words(text: str) -> list[str]:
    """Return the generated region's words, so formatter rewrapping cannot cause drift."""
    return text.split(START)[1].split(END)[0].split()


app = App(help=__doc__.splitlines()[0], config=cyclopts.config.Env('INPUT_', command=False))


@app.default
def main(*, check: bool = False, register: Path = ROOT / 'spec/decisions.json',
         document: Path = ROOT / 'docs/decision-register.md') -> int:
    """Write or check the generated region; e.g. ``main(check=True)`` returns 1 after a hand edit.

    Parameters
    ----------
    check
        Compare instead of writing; exit 1 when the document has drifted.
    register
        The JSON master to render.
    document
        The Markdown register whose generated region is written or compared.
    """
    text = document.read_text(encoding='utf-8')
    try:
        expected = splice(text, render(json.loads(register.read_text(encoding='utf-8'))))
    except MarkerError as error:
        print(f'{document}: {error}', file=sys.stderr)
        return 2
    if not check:
        document.write_text(expected, encoding='utf-8')
        return 0
    if region_words(text) == region_words(expected):
        print(f'{document.name} matches {register.name}.')
        return 0
    print(f'{document.name} has drifted from {register.name}: run scripts/generate_decisions.py', file=sys.stderr)
    return 1


if __name__ == '__main__':
    app()
