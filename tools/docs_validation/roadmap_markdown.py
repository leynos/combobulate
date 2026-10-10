"""Export the canonical Markdown roadmap to its derived JSON view.

`docs/roadmap.md` is canonical. This module parses the region between the
roadmap markers with Wenmode's GitHub-flavoured rules and rebuilds the phase,
step, and task structure that the design checks consume. Structure it does not
recognize fails with the source line rather than being dropped, so the JSON
view can never silently omit roadmap content. Upstream request
leynos/mapsplice#144 tracks a native export that will replace this module.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass

from wenmode import Wenmode, presets
from wenmode.nodes import Node

START = '<!-- roadmap:start -->'
END = '<!-- roadmap:end -->'
DESIGN_REF = ' See `technical-design.md` '
TASK_STATUS = {False: 'open', True: 'done'}
PARSER = Wenmode(presets.github(), positions=True)


class RoadmapStructureError(ValueError):
    """Report unrecognized roadmap structure; e.g. a level-four heading at line 12."""

    def __init__(self, message: str, line: int | None = None) -> None:
        self.line = line
        super().__init__(f'docs/roadmap.md:{line}: {message}' if line else message)


@dataclass(frozen=True)
class Source:
    """Map region offsets to file lines; e.g. Source(text, 40).line_of(0) is the region's first line."""

    text: str
    offset: int

    def line_of(self, node: Node) -> int:
        """Return the 1-based file line where a node starts."""
        return self.text.count('\n', 0, self.offset + node.position.start) + 1

    def fail(self, node: Node, message: str) -> RoadmapStructureError:
        """Build an error naming the node's source line."""
        return RoadmapStructureError(message, self.line_of(node))


def inline_text(node: Node, source: Source) -> str:
    """Flatten inline content to single-spaced text; inline code keeps its backticks."""
    parts: list[str] = []
    for child in node.children:
        if child.type == 'text':
            parts.append(child.value)
        elif child.type == 'inlineCode':
            parts.append(f'`{child.value}`')
        else:
            raise source.fail(child, f'unsupported inline {child.type}')
    return ' '.join(''.join(parts).split())


def labelled(text: str, label: str, node: Node, source: Source) -> str:
    """Strip a required label; e.g. labelled('Idea: x', 'Idea: ', ...) returns 'x'."""
    if not text.startswith(label):
        raise source.fail(node, f'expected a paragraph starting {label!r}')
    return text.removeprefix(label)


def numbered(text: str, pattern: str, node: Node, source: Source) -> tuple[str, str]:
    """Split a numbered title; e.g. '1.2. Step' gives ('1.2', 'Step')."""
    match = re.fullmatch(rf'({pattern})\. (.+)', text)
    if match is None:
        raise source.fail(node, f'malformed numbered title {text!r}')
    return match.group(1), match.group(2)


def split_design_ref(text: str, node: Node, source: Source) -> tuple[str, str]:
    """Split trailing design sections; e.g. 'Why? See `technical-design.md` §§1-2.'."""
    head, marker, sections = text.rpartition(DESIGN_REF)
    if not marker or not sections.endswith('.'):
        raise source.fail(node, 'expected a trailing technical-design reference')
    return head, sections.removesuffix('.')


def id_list(text: str) -> list[str]:
    """Split a comma-separated identifier list; e.g. 'B01, B02.' gives ['B01', 'B02']."""
    return [part.strip() for part in text.removesuffix('.').split(',') if part.strip()]


def item_paragraph(item: Node, source: Source) -> tuple[str, list[Node]]:
    """Return a list item's lead text and any nested lists."""
    lead, *rest = item.children
    if lead.type != 'paragraph' or any(node.type != 'list' for node in rest):
        raise source.fail(item, 'expected one paragraph followed only by nested lists')
    return inline_text(lead, source), rest


def apply_bullet(task: dict, item: Node, source: Source) -> None:
    """Fold one labelled task sub-bullet into the task record."""
    text, nested = item_paragraph(item, source)
    if nested:
        raise source.fail(item, 'task sub-bullets must not nest further')
    if item.checked is not None:
        if item.checked:
            raise source.fail(item, 'detail checkboxes are not tracked; tick the task instead')
        task['details'].append(text)
    elif text.startswith('Requires '):
        task['requires'] = id_list(text.removeprefix('Requires '))
    elif text.startswith('See `technical-design.md` '):
        task['sections'] = text.removeprefix('See `technical-design.md` ').removesuffix('.')
    elif text.startswith('Proof first: '):
        proof, marker, bets = text.removeprefix('Proof first: ').rpartition(' Bets: ')
        if not marker:
            raise source.fail(item, 'proof-first bullet must end with its bets')
        task['proof_first'], task['bets'] = proof, id_list(bets)
    elif text.startswith('Success: '):
        task['success'] = text.removeprefix('Success: ')
    else:
        raise source.fail(item, f'unrecognized task bullet {text[:40]!r}')


def parse_task(item: Node, source: Source) -> dict:
    """Build one task from a checkbox list item and its labelled sub-bullets."""
    if item.checked is None:
        raise source.fail(item, 'tasks must be checkbox items')
    text, nested = item_paragraph(item, source)
    task_id, title = numbered(text, r'\d+\.\d+\.\d+', item, source)
    task = {'id': task_id, 'title': title, 'requires': [], 'sections': '', 'success': '', 'details': [],
            'proof_first': '', 'bets': [], 'status': TASK_STATUS[item.checked]}
    for sub_list in nested:
        for sub_item in sub_list.children:
            apply_bullet(task, sub_item, source)
    return task


def parse_phase_header(heading: Node, paragraphs: list[Node], source: Source) -> dict:
    """Build a phase from its heading and its idea, goals, context, and gate paragraphs."""
    if len(paragraphs) != 4:
        raise source.fail(heading, 'a phase needs Idea, Goals, context, and Gate paragraphs')
    idea, goals, context, gate = (inline_text(node, source) for node in paragraphs)
    number, title = numbered(inline_text(heading, source), r'\d+', heading, source)
    goal_text = labelled(goals, 'Goals: ', paragraphs[1], source)
    goal_list, marker, _ = goal_text.partition(' in `terms-of-reference.md`')
    if not marker:
        raise source.fail(paragraphs[1], 'goals must cite `terms-of-reference.md`')
    return {'number': int(number), 'title': title, 'idea': labelled(idea, 'Idea: ', paragraphs[0], source),
            'goals': id_list(goal_list), 'gate': labelled(gate, 'Gate: ', paragraphs[3], source),
            'context': context, 'steps': []}


def blocks(root: Node, source: Source) -> Iterator[tuple[Node, list[Node]]]:
    """Group top-level nodes into (heading, following nodes) sections."""
    heading: Node | None = None
    body: list[Node] = []
    for node in root.children:
        if node.type == 'heading':
            if heading is not None:
                yield heading, body
            if node.depth not in (2, 3):
                raise source.fail(node, f'unexpected level-{node.depth} heading')
            heading, body = node, []
        elif heading is None:
            raise source.fail(node, 'content before the first phase heading')
        else:
            body.append(node)
    if heading is not None:
        yield heading, body


def parse_step(heading: Node, body: list[Node], phase: dict, source: Source) -> dict:
    """Build a step from its heading, question paragraph, and task list."""
    if len(body) != 2 or body[0].type != 'paragraph' or body[1].type != 'list':
        raise source.fail(heading, 'a step needs one question paragraph and one task list')
    number, title = numbered(inline_text(heading, source), r'\d+\.\d+', heading, source)
    question, sections = split_design_ref(inline_text(body[0], source), body[0], source)
    if not number.startswith(f"{phase['number']}."):
        raise source.fail(heading, f'step {number} is outside phase {phase["number"]}')
    return {'number': number, 'title': title, 'question': question, 'sections': sections,
            'tasks': [parse_task(item, source) for item in body[1].children]}


def roadmap_region(text: str) -> tuple[str, int]:
    """Return the marked region and its offset; exactly one marker pair is required."""
    if text.count(START) != 1 or text.count(END) != 1:
        raise RoadmapStructureError('docs/roadmap.md needs exactly one roadmap marker pair')
    begin = text.index(START) + len(START)
    return text[begin:text.index(END)], begin


def overall_status(phases: list[dict]) -> str:
    """Summarize tick state; e.g. no ticked task gives 'proposed-all-tasks-open'."""
    statuses = {task['status'] for phase in phases for step in phase['steps'] for task in step['tasks']}
    if statuses <= {'open'}:
        return 'proposed-all-tasks-open'
    return 'all-tasks-done' if statuses == {'done'} else 'tasks-in-progress'


def parse_roadmap(text: str) -> dict:
    """Export the canonical roadmap; e.g. parse_roadmap(path.read_text())['phases'][0]['number'] == 1."""
    region, offset = roadmap_region(text)
    source = Source(text, offset)
    revision = re.search(r'^Revision (\d+\.\d+),', text, re.M)
    if revision is None:
        raise RoadmapStructureError('docs/roadmap.md needs a "Revision N.N," preamble line')
    phases: list[dict] = []
    for heading, body in blocks(PARSER.parse(region), source):
        if heading.depth == 2:
            phases.append(parse_phase_header(heading, body, source))
        elif not phases:
            raise source.fail(heading, 'step heading before any phase heading')
        else:
            phases[-1]['steps'].append(parse_step(heading, body, phases[-1], source))
    return {'revision': revision.group(1), 'status': overall_status(phases), 'phases': phases}


def export_text(text: str) -> str:
    """Serialize the export exactly as committed: two-space indent, UTF-8, final newline."""
    return json.dumps(parse_roadmap(text), indent=2, ensure_ascii=False) + '\n'
