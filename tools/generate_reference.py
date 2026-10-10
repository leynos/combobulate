#!/usr/bin/env python3
"""Regenerate reference tables from the proposed JSON catalogue.

Usage: python tools/generate_reference.py [--check]
The human-authored preamble and semantic cases remain outside generated markers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from docs_validation.markdown import generated_matches

ROOT = Path(__file__).resolve().parents[1]
START = '<!-- catalogue:start -->'
END = '<!-- catalogue:end -->'
GROUPS = [
    'Verbs', 'Conjunctions', 'Operator modifiers', 'Policy modifiers',
    'Macros', 'Execution and extension interfaces',
]

def escape(value: str) -> str:
    return value.replace('|', r'\|').replace('\n', ' ')

def group_chunks(group: str, entries: list[dict[str, object]]) -> list[tuple[str | None, list[dict[str, object]]]]:
    """Partition verbs into semantic families; other groups retain one table."""
    selected = [row for row in entries if row['group'] == group]
    if group != 'Verbs':
        return [(None, selected)]
    boundaries = [
        ('Scalar arithmetic', 'add', 'eq'),
        ('Predicates, Boolean logic, and casts', 'eq', 'identity'),
        ('Values and structural transformations', 'identity', 'sort_up'),
        ('Ordering and selection', 'sort_up', 'sum'),
        ('Whole-cell aggregates', 'sum', 'matmul'),
        ('Products and typed collections', 'matmul', None),
    ]
    indexes = {str(row['name']): i for i, row in enumerate(selected)}
    return [(name, selected[indexes[first]:indexes[last] if last else None])
            for name, first, last in boundaries]


def render_table(rows: list[dict[str, object]]) -> str:
    """Render one catalogue table; literal pipes use Markdown table escapes."""
    output = [
        '| ID / name | Signature | Shape | Contract and edge cases | '
        'Execution | Scope / tasks |\n'
        '| --- | --- | --- | --- | --- | --- |\n'
    ]
    for row in rows:
        tasks = ', '.join(str(task) for task in row.get('roadmap_tasks', []))
        cells = [
            f"{row['id']} `{escape(str(row['name']))}`",
            f"`{escape(str(row['signature']))}`",
            escape(str(row['shape'])), escape(str(row['contract'])),
            escape(str(row['execution'])), f"{row['scope']}; {tasks}",
        ]
        output.append('| ' + ' | '.join(cells) + ' |\n')
    return ''.join(output) + '\n'


def render(entries: list[dict[str, object]]) -> str:
    """Render grouped catalogue tables; human preamble stays outside the markers."""
    output: list[str] = []
    for section, group in enumerate(GROUPS, 2):
        output.append(f'## {section}. {group[0].lower() + group[1:]}\n\n')
        for title, rows in group_chunks(group, entries):
            if title:
                output.append(f'### {title[0].lower() + title[1:]}\n\n')
            output.append(render_table(rows))
    return ''.join(output).rstrip()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    source = json.loads((ROOT / 'spec/vocabulary.json').read_text())
    path = ROOT / 'docs/language-reference.md'
    current = path.read_text()
    if current.count(START) != 1 or current.count(END) != 1:
        raise SystemExit('Reference must have exactly one pair of catalogue markers.')
    before, body = current.split(START)
    _, after = body.split(END)
    expected = before + START + '\n\n' + render(source['entries']) + '\n\n' + END + after
    if args.check:
        if not generated_matches(current, render(source['entries']), START, END):
            raise SystemExit('Reference tables differ from spec/vocabulary.json.')
        print(f"Reference tables match {len(source['entries'])} catalogue entries.")
    else:
        path.write_text(expected)
        print(f"Regenerated {len(source['entries'])} catalogue entries.")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
