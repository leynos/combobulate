"""Render roadmap structures in the canonical layout, for round-trip tests only.

This independent renderer preserves the layout that the retired JSON-to-Markdown
generator emitted. Tests render generated structures with it and require the
Markdown exporter to recover them, so the exporter is checked against a layout
it did not produce. It must not become a production path: `docs/roadmap.md`
is canonical and edited directly.
"""
from __future__ import annotations

import textwrap

from export_roadmap import END, START

CHECKBOX = {'open': '- [ ] ', 'done': '- [x] '}


def paragraph(text: str) -> str:
    """Wrap one paragraph at 80 columns; e.g. paragraph('Idea: x') ends with a blank line."""
    return textwrap.fill(text, width=80, break_long_words=False, break_on_hyphens=False) + '\n\n'


def bullet(text: str, prefix: str, subsequent: str) -> str:
    """Wrap one list item with hanging indentation; e.g. bullet('x', '- ', '  ')."""
    return textwrap.fill(text, width=80, initial_indent=prefix, subsequent_indent=subsequent,
                         break_long_words=False, break_on_hyphens=False) + '\n'


def render_task(task: dict) -> str:
    """Render one task and its labelled sub-bullets in canonical order."""
    lines = [bullet(f"{task['id']}. {task['title']}", CHECKBOX[task['status']], '  ')]
    if task['requires']:
        lines.append(bullet('Requires ' + ', '.join(task['requires']) + '.', '  - ', '    '))
    lines.append(bullet(f"See `technical-design.md` {task['sections']}.", '  - ', '    '))
    lines.extend(bullet(detail, '  - [ ] ', '    ') for detail in task['details'])
    lines.append(bullet(f"Proof first: {task['proof_first']} Bets: {', '.join(task['bets'])}.", '  - ', '    '))
    lines.append(bullet('Success: ' + task['success'], '  - ', '    '))
    return ''.join(lines)


def render_phase(phase: dict) -> str:
    """Render one phase with its labelled paragraphs, steps, and tasks."""
    output = [f"## {phase['number']}. {phase['title']}\n\n",
              paragraph('Idea: ' + phase['idea']),
              paragraph('Goals: ' + ', '.join(phase['goals']) + ' in `terms-of-reference.md` §6.'),
              paragraph(phase['context']),
              paragraph('Gate: ' + phase['gate'])]
    for step in phase['steps']:
        output.append(f"### {step['number']}. {step['title']}\n\n")
        output.append(paragraph(f"{step['question']} See `technical-design.md` {step['sections']}."))
        output.extend(render_task(task) for task in step['tasks'])
        output.append('\n')
    return ''.join(output)


def render_document(structure: dict) -> str:
    """Render a complete roadmap document, including its revision line and markers."""
    body = ''.join(render_phase(phase) for phase in structure['phases']).rstrip()
    return (f"# Roadmap\n\nRevision {structure['revision']}, 6 October 2026.\n\n"
            f'{START}\n\n{body}\n\n{END}\n')
