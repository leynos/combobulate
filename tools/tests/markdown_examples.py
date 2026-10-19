"""Load marked JSON examples from their published Markdown source.

This helper is scoped to documentation contract tests. It requires every fenced
block in the selected document to have a unique adjacent marker and parses the
example from the file readers see, rather than from a copied fixture.
"""
from __future__ import annotations

import json
import re
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


def _consume_active_line(path: Path, line: str, active: tuple[str, str, int], body: list[str],
                         examples: dict[str, dict[str, object]]) -> tuple[str, str, int] | None:
    """Append fence content or close it; e.g. a closing line stores the object and returns ``None``."""
    if _is_closing_fence(line, active[0]):
        _record_example(path, active, body, examples)
        body.clear()
        return None
    body.append(line)
    return active


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


def load_marked_json_examples(path: Path) -> dict[str, dict[str, object]]:
    """Read unique, marked JSON fences from a Markdown document.

    For example, ``load_marked_json_examples(Path('migration.md'))['evidence-v2']``
    returns the parsed object from that published example.
    """
    examples: dict[str, dict[str, object]] = {}
    pending: str | None = None
    active: tuple[str, str, int] | None = None
    body: list[str] = []

    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
        if active is not None:
            active = _consume_active_line(path, line, active, body, examples)
            continue

        marker = MARKER.fullmatch(line)
        if marker:
            pending = _read_marker(path, number, marker, pending)
            continue

        opening = FENCE.fullmatch(line)
        if opening:
            active = _start_example(path, number, opening, pending)
            pending = None
            continue

        if pending is not None:
            raise ValueError(f'{path}:{number}: tested-example marker must be adjacent to its fence')

    _finish_examples(path, examples, pending, active)
    return examples
