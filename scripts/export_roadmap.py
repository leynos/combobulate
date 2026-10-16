#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["cyclopts==5.2.0", "wenmode==0.15.2"]
# ///
"""Export the canonical `docs/roadmap.md` to its derived `spec/roadmap.json` view.

`docs/roadmap.md` is canonical. This script parses the region between the
roadmap markers with Wenmode's GitHub-flavoured rules and rebuilds the phase,
step, and task structure that the design checks consume. Structure it does not
recognize fails with the source line rather than being dropped, so the JSON
view can never silently omit roadmap content.

Run ``scripts/export_roadmap.py`` after editing the roadmap to rewrite the
export, or ``scripts/export_roadmap.py --check`` (``INPUT_CHECK=true`` in CI)
to fail when the committed export has drifted. Exit codes: 0 when the export
is written or matches, 1 on drift (a unified diff is printed), and 2 when the
roadmap structure is malformed (the source line is printed). The design
checker imports `parse_roadmap` from this file, so the parser has one home.
Upstream request leynos/mapsplice#144 tracks a native replacement.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import cyclopts
from cyclopts import App
from wenmode import Wenmode, presets
from wenmode.nodes import Node

ROOT = Path(__file__).resolve().parents[1]

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
    if node.type not in {'paragraph', 'heading'}:
        raise source.fail(node, f'unsupported block {node.type}')
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


def is_detail_bullet(task: dict, item: Node, text: str, source: Source) -> bool:
    """Append an unchecked detail; e.g. `- [ ] Context.` adds a detail string."""
    if item.checked is None:
        return False
    if item.checked:
        raise source.fail(item, 'detail checkboxes are not tracked; tick the task instead')
    task['details'].append(text)
    return True


TaskField = tuple[str, object, list[str] | None]


def parse_requires_field(text: str) -> TaskField:
    """Parse a task dependency field; e.g. `Requires T1.` becomes `['T1']`."""
    return 'requires', id_list(text.removeprefix('Requires ')), None


def parse_sections_field(text: str) -> TaskField:
    """Parse a task design reference; e.g. `See ... §§1.` becomes `sections='§§1'`."""
    sections = text.removeprefix('See `technical-design.md` ').removesuffix('.')
    return 'sections', sections, None


def parse_proof_field(text: str, item: Node, source: Source) -> TaskField:
    """Parse proof and bets together; e.g. `Proof first: x Bets: B01` yields both fields."""
    proof, marker, bets = text.removeprefix('Proof first: ').rpartition(' Bets: ')
    if not marker:
        raise source.fail(item, 'proof-first bullet must end with its bets')
    if not proof:
        raise source.fail(item, 'proof-first bullet must include its proof')
    bet_ids = id_list(bets)
    if not bet_ids:
        raise source.fail(item, 'proof-first bullet must include at least one bet')
    return 'proof_first', proof, bet_ids


def parse_success_field(text: str) -> TaskField:
    """Parse a task success field; e.g. `Success: x` yields `('success', 'x', None)`."""
    return 'success', text.removeprefix('Success: '), None


def parse_task_field(text: str, item: Node, source: Source) -> TaskField:
    """Parse one task field; e.g. `Success: x` yields `('success', 'x', None)`."""
    parsers: tuple[tuple[str, Callable[[str], TaskField]], ...] = (
        ('Requires ', parse_requires_field),
        ('See `technical-design.md` ', parse_sections_field),
        ('Proof first: ', lambda value: parse_proof_field(value, item, source)),
        ('Success: ', parse_success_field),
    )
    for prefix, parser in parsers:
        if text.startswith(prefix):
            return parser(text)
    raise source.fail(item, f'unrecognized task bullet {text[:40]!r}')


def apply_bullet(task: dict, item: Node, source: Source, seen_fields: set[str]) -> None:
    """Fold one labelled task sub-bullet into the task record."""
    text, nested = item_paragraph(item, source)
    if nested:
        raise source.fail(item, 'task sub-bullets must not nest further')
    if is_detail_bullet(task, item, text, source):
        return
    field, value, bets = parse_task_field(text, item, source)
    if field in seen_fields:
        raise source.fail(item, f'duplicate task {field} bullet')
    seen_fields.add(field)
    task[field] = value
    if bets is not None:
        task['bets'] = bets


def task_sub_items(nested: list[Node]) -> Iterator[Node]:
    """Yield task sub-bullets; e.g. flatten each nested list into one sequence."""
    for sub_list in nested:
        yield from sub_list.children


def require_task_fields(item: Node, seen_fields: set[str], source: Source) -> None:
    """Require each contract field; e.g. a task without `Success:` fails at its line."""
    required_fields = (
        ('sections', 'technical-design reference'),
        ('proof_first', 'proof-first'),
        ('success', 'success'),
    )
    for field, label in required_fields:
        if field not in seen_fields:
            raise source.fail(item, f'task is missing its {label} bullet')


def parse_task(item: Node, source: Source) -> dict:
    """Build one task from a checkbox list item and its labelled sub-bullets."""
    if item.checked is None:
        raise source.fail(item, 'tasks must be checkbox items')
    text, nested = item_paragraph(item, source)
    task_id, title = numbered(text, r'\d+\.\d+\.\d+', item, source)
    task = {'id': task_id, 'title': title, 'requires': [], 'sections': '', 'success': '', 'details': [],
            'proof_first': '', 'bets': [], 'status': TASK_STATUS[item.checked]}
    seen_fields: set[str] = set()
    for sub_item in task_sub_items(nested):
        apply_bullet(task, sub_item, source, seen_fields)
    require_task_fields(item, seen_fields, source)
    return task


def parse_phase_header(heading: Node, paragraphs: list[Node], source: Source) -> dict:
    """Build a phase from its heading and its idea, goals, context, and gate paragraphs."""
    if len(paragraphs) != 4:
        raise source.fail(heading, 'a phase needs Idea, Goals, context, and Gate paragraphs')
    idea, goals, context, gate = (inline_text(node, source) for node in paragraphs)
    number, title = numbered(inline_text(heading, source), r'\d+', heading, source)
    goal_text = labelled(goals, 'Goals: ', paragraphs[1], source)
    goal_match = re.fullmatch(r'(.+) in `terms-of-reference\.md` §6\.', goal_text)
    if goal_match is None:
        raise source.fail(paragraphs[1], 'goals must end with `terms-of-reference.md` §6.')
    return {'number': int(number), 'title': title, 'idea': labelled(idea, 'Idea: ', paragraphs[0], source),
            'goals': id_list(goal_match.group(1)), 'gate': labelled(gate, 'Gate: ', paragraphs[3], source),
            'context': context, 'steps': []}


def collect_block_node(node: Node, heading: Node | None, body: list[Node],
                       source: Source) -> tuple[tuple[Node, list[Node]] | None, Node | None, list[Node]]:
    """Add a node to its section; e.g. a heading closes the previous section."""
    if node.type != 'heading':
        if heading is None:
            raise source.fail(node, 'content before the first phase heading')
        body.append(node)
        return None, heading, body
    if node.depth not in (2, 3):
        raise source.fail(node, f'unexpected level-{node.depth} heading')
    completed = (heading, body) if heading is not None else None
    return completed, node, []


def blocks(root: Node, source: Source) -> Iterator[tuple[Node, list[Node]]]:
    """Group top-level nodes into (heading, following nodes) sections."""
    heading: Node | None = None
    body: list[Node] = []
    for node in root.children:
        completed, heading, body = collect_block_node(node, heading, body, source)
        if completed is not None:
            yield completed
    if heading is not None:
        yield heading, body


def step_body(heading: Node, body: list[Node], source: Source) -> tuple[Node, Node]:
    """Validate and split step content; e.g. return its question and task list."""
    if len(body) != 2:
        raise source.fail(heading, 'a step needs one question paragraph and one task list')
    question, tasks = body
    if question.type != 'paragraph':
        raise source.fail(heading, 'a step needs one question paragraph before its task list')
    if tasks.type != 'list':
        raise source.fail(heading, 'a step needs one task list after its question paragraph')
    return question, tasks


def step_number(heading: Node, phase: dict, source: Source) -> tuple[str, str]:
    """Validate a step's phase prefix; e.g. phase 1 accepts `1.2. Step`."""
    number, title = numbered(inline_text(heading, source), r'\d+\.\d+', heading, source)
    if not number.startswith(f"{phase['number']}."):
        raise source.fail(heading, f'step {number} is outside phase {phase["number"]}')
    return number, title


def parse_step(heading: Node, body: list[Node], phase: dict, source: Source) -> dict:
    """Build a step from its heading, question paragraph, and task list."""
    question_node, task_list = step_body(heading, body, source)
    number, title = step_number(heading, phase, source)
    question, sections = split_design_ref(inline_text(question_node, source), question_node, source)
    return {'number': number, 'title': title, 'question': question, 'sections': sections,
            'tasks': [parse_task(item, source) for item in task_list.children]}


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


@dataclass
class RoadmapBuilder:
    """Accumulate parsed phases; e.g. add blocks before validating empty phases."""

    source: Source
    phases: list[dict] = field(default_factory=list)
    phase_headings: list[Node] = field(default_factory=list)

    def add_block(self, heading: Node, body: list[Node]) -> None:
        """Add one phase or step; e.g. a level-three heading appends a phase step."""
        if heading.depth == 2:
            self.phases.append(parse_phase_header(heading, body, self.source))
            self.phase_headings.append(heading)
        elif not self.phases:
            raise self.source.fail(heading, 'step heading before any phase heading')
        else:
            phase = self.phases[-1]
            phase['steps'].append(parse_step(heading, body, phase, self.source))

    def require_nonempty_phases(self) -> None:
        """Require a populated roadmap; e.g. an empty phase fails at its heading."""
        if not self.phases:
            raise RoadmapStructureError('docs/roadmap.md needs at least one phase')
        for phase, heading in zip(self.phases, self.phase_headings, strict=True):
            if not phase['steps']:
                raise self.source.fail(heading, f'phase {phase["number"]} needs at least one step')


def parse_roadmap(text: str) -> dict:
    """Export the canonical roadmap; e.g. parse_roadmap(path.read_text())['phases'][0]['number'] == 1."""
    region, offset = roadmap_region(text)
    source = Source(text, offset)
    revision = re.search(r'^Revision (\d+\.\d+),', text, re.M)
    if revision is None:
        raise RoadmapStructureError('docs/roadmap.md needs a "Revision N.N," preamble line')
    roadmap = RoadmapBuilder(source)
    for heading, body in blocks(PARSER.parse(region), source):
        roadmap.add_block(heading, body)
    roadmap.require_nonempty_phases()
    return {'revision': revision.group(1), 'status': overall_status(roadmap.phases), 'phases': roadmap.phases}


def export_text(text: str) -> str:
    """Serialize the export exactly as committed: two-space indent, UTF-8, final newline."""
    return json.dumps(parse_roadmap(text), indent=2, ensure_ascii=False) + '\n'


def drift(committed: str, fresh: str) -> str:
    """Render the difference between the committed and fresh exports."""
    return ''.join(difflib.unified_diff(committed.splitlines(keepends=True), fresh.splitlines(keepends=True),
                                        'spec/roadmap.json (committed)', 'spec/roadmap.json (fresh export)'))


app = App(help=__doc__.splitlines()[0], config=cyclopts.config.Env('INPUT_', command=False))


@app.default
def main(*, check: bool = False, roadmap: Path = ROOT / 'docs/roadmap.md',
         export: Path = ROOT / 'spec/roadmap.json') -> int:
    """Write or check the export; e.g. ``main(check=True)`` returns 1 after an unexported edit.

    Parameters
    ----------
    check
        Compare instead of writing; exit 1 when the committed export has drifted.
    roadmap
        The canonical Markdown roadmap to read.
    export
        The derived JSON view to write or compare.
    """
    try:
        fresh = export_text(roadmap.read_text(encoding='utf-8'))
    except RoadmapStructureError as error:
        print(error, file=sys.stderr)
        return 2
    if not check:
        export.write_text(fresh, encoding='utf-8')
        return 0
    committed = export.read_text(encoding='utf-8') if export.exists() else ''
    if committed == fresh:
        print(f'{export.name} matches {roadmap.name}.')
        return 0
    print(drift(committed, fresh), end='')
    print('The roadmap export is stale: run scripts/export_roadmap.py', file=sys.stderr)
    return 1


if __name__ == '__main__':
    app()
