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
            fence, identifier, start_line = active
            if line.startswith(fence) and not line[len(fence):].strip():
                if identifier in examples:
                    raise ValueError(f'{path}:{start_line}: duplicate tested-example marker {identifier!r}')
                example = json.loads('\n'.join(body))
                if not isinstance(example, dict):
                    raise ValueError(f'{path}:{start_line}: JSON example {identifier!r} must be an object')
                examples[identifier] = example
                active = None
                body.clear()
            else:
                body.append(line)
            continue

        marker = MARKER.fullmatch(line)
        if marker:
            if pending is not None:
                raise ValueError(f'{path}:{number}: tested-example marker is not followed by a fence')
            pending = marker.group(1)
            continue

        opening = FENCE.fullmatch(line)
        if opening:
            if pending is None:
                raise ValueError(f'{path}:{number}: fenced examples must have tested-example markers')
            if opening.group('language').lower() != 'json':
                raise ValueError(f'{path}:{number}: only JSON examples are supported')
            active = (opening.group('ticks'), pending, number)
            pending = None
            continue

        if pending is not None:
            raise ValueError(f'{path}:{number}: tested-example marker must be adjacent to its fence')

    if active is not None:
        raise ValueError(f'{path}:{active[2]}: unterminated tested-example fence')
    if pending is not None:
        raise ValueError(f'{path}: tested-example marker is not followed by a fence')
    if not examples:
        raise ValueError(f'{path}: no tested JSON examples found')
    return examples
