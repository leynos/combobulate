#!/usr/bin/env python3
"""Render the GIST roadmap from its reviewable JSON task ledger."""
from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

from docs_validation.markdown import generated_matches

ROOT = Path(__file__).resolve().parents[1]
START = '<!-- roadmap:start -->'
END = '<!-- roadmap:end -->'

def paragraph(text: str) -> str:
    return textwrap.fill(text, width=80, break_long_words=False, break_on_hyphens=False) + '\n\n'

def bullet(text: str, prefix: str, subsequent: str) -> str:
    return textwrap.fill(text, width=80, initial_indent=prefix, subsequent_indent=subsequent,
                         break_long_words=False, break_on_hyphens=False) + '\n'

def render(phases: list[dict]) -> str:
    output: list[str] = []
    for phase in phases:
        output.append(f"## {phase['number']}. {phase['title']}\n\n")
        output.append(paragraph('Idea: ' + phase['idea']))
        output.append(paragraph('Goals: ' + ', '.join(phase['goals']) +
                                ' in `terms-of-reference.md` §6.'))
        output.append(paragraph(phase['context']))
        output.append(paragraph('Gate: ' + phase['gate']))
        for step in phase['steps']:
            output.append(f"### {step['number']}. {step['title']}\n\n")
            output.append(paragraph(step['question'] +
                                    f" See `technical-design.md` {step['sections']}."))
            for task in step['tasks']:
                output.append(bullet(task['id'] + '. ' + task['title'], '- [ ] ', '  '))
                if task['requires']:
                    output.append(bullet('Requires ' + ', '.join(task['requires']) + '.', '  - ', '    '))
                output.append(bullet(f"See `technical-design.md` {task['sections']}.", '  - ', '    '))
                for detail in task.get('details', []):
                    output.append(bullet(detail, '  - [ ] ', '    '))
                proof = task.get('proof_first', '')
                if proof:
                    bet_refs = ', '.join(task.get('bets', []))
                    output.append(bullet('Proof first: ' + proof + ' Bets: ' + bet_refs + '.', '  - ', '    '))
                output.append(bullet('Success: ' + task['success'], '  - ', '    '))
            output.append('\n')
    return ''.join(output).rstrip()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    data = json.loads((ROOT/'spec/roadmap.json').read_text())
    path = ROOT/'docs/roadmap.md'
    current = path.read_text()
    if current.count(START) != 1 or current.count(END) != 1:
        raise SystemExit('Roadmap needs exactly one marker pair.')
    before, remaining = current.split(START)
    _, after = remaining.split(END)
    expected = before + START + '\n\n' + render(data['phases']) + '\n\n' + END + after
    if args.check:
        if not generated_matches(current, render(data['phases']), START, END):
            raise SystemExit('Roadmap differs from spec/roadmap.json.')
        print('Roadmap matches the task ledger.')
    else:
        path.write_text(expected)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
