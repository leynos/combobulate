"""Load marked JSON examples from their published Markdown source.

This helper is scoped to documentation contract tests. It requires every fenced
block in the selected document to have a unique adjacent marker and parses the
example from the file readers see, rather than from a copied fixture.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MARKER = re.compile(r'<!-- tested-example: ([a-z0-9-]+) -->$')
FENCE = re.compile(r'(?P<ticks>`{3,}|~{3,})(?P<language>[a-zA-Z0-9_-]+)\s*$')


def _is_closing_fence(line: str, fence: str) -> bool:
    """Recognise a matching fence terminator; e.g. ``'```'`` closes ``'```'``."""
    return line.startswith(fence) and not line[len(fence):].strip()


def _record_example(path: Path, active: tuple[str, str, int], body: list[str],
                    examples: dict[str, dict[str, object]]) -> None:
    """Validate and store one closed example; e.g. a marked JSON object is indexed by its marker."""
    _, identifier, start_line = active
    if identifier in examples:
        raise ValueError(f'{path}:{start_line}: duplicate tested-example marker {identifier!r}')
    example = json.loads('\n'.join(body))
    if not isinstance(example, dict):
        raise ValueError(f'{path}:{start_line}: JSON example {identifier!r} must be an object')
    examples[identifier] = example


def _read_marker(path: Path, number: int, marker: re.Match[str], pending: str | None) -> str:
    """Accept the next example marker; e.g. a second pending marker raises ``ValueError``."""
    if pending is not None:
        raise ValueError(f'{path}:{number}: tested-example marker is not followed by a fence')
    return marker.group(1)


def _start_example(path: Path, number: int, opening: re.Match[str], pending: str | None) -> tuple[str, str, int]:
    """Validate and start a marked JSON fence; e.g. a marker plus ``json`` returns its fence state."""
    if pending is None:
        raise ValueError(f'{path}:{number}: fenced examples must have tested-example markers')
    if opening.group('language').lower() != 'json':
        raise ValueError(f'{path}:{number}: only JSON examples are supported')
    return opening.group('ticks'), pending, number


def _finish_examples(path: Path, examples: dict[str, dict[str, object]], pending: str | None,
                     active: tuple[str, str, int] | None) -> None:
    """Reject incomplete documents; e.g. an open fence reports its opening line."""
    if active is not None:
        raise ValueError(f'{path}:{active[2]}: unterminated tested-example fence')
    if pending is not None:
        raise ValueError(f'{path}: tested-example marker is not followed by a fence')
    if not examples:
        raise ValueError(f'{path}: no tested JSON examples found')


@dataclass
class _MarkedExampleReader:
    """Hold the state for reading marked JSON fences from one document."""

    path: Path
    examples: dict[str, dict[str, object]] = field(default_factory=dict)
    pending: str | None = None
    active: tuple[str, str, int] | None = None
    body: list[str] = field(default_factory=list)

    def _consume_active_line(self, line: str) -> None:
        """Append fence content or close the active example."""
        if _is_closing_fence(line, self.active[0]):
            _record_example(self.path, self.active, self.body, self.examples)
            self.body.clear()
            self.active = None
        else:
            self.body.append(line)

    def consume_line(self, number: int, line: str) -> None:
        """Advance the document parser by one line."""
        if self.active is not None:
            self._consume_active_line(line)
            return

        marker = MARKER.fullmatch(line)
        if marker:
            self.pending = _read_marker(self.path, number, marker, self.pending)
            return

        opening = FENCE.fullmatch(line)
        if opening:
            self.active = _start_example(self.path, number, opening, self.pending)
            self.pending = None
            return

        if self.pending is not None:
            raise ValueError(f'{self.path}:{number}: tested-example marker must be adjacent to its fence')

    def finish(self) -> dict[str, dict[str, object]]:
        """Validate end-of-document state and return the parsed examples."""
        _finish_examples(self.path, self.examples, self.pending, self.active)
        return self.examples


def load_marked_json_examples(path: Path) -> dict[str, dict[str, object]]:
    """Read unique, marked JSON fences from a Markdown document.

    For example, ``load_marked_json_examples(Path('migration.md'))['evidence-v2']``
    returns the parsed object from that published example.
    """
    reader = _MarkedExampleReader(path)
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
        reader.consume_line(number, line)
    return reader.finish()
