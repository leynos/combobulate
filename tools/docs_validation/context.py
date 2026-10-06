"""Own explicit design-pack inputs and validation reporting.

Feature checks accept one context, so tests can supply an isolated repository
without changing process globals. Only the checker composition root writes reports.
"""
from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

DESIGN_DOCUMENTS = (
    'context.md', 'language-reference.md', 'references.md', 'revision-0.2.md',
    'roadmap.md', 'technical-design.md', 'terms-of-reference.md',
    'testable-bets.md', 'validation.md',
)
DOCUMENT_REPORTS = ('revision-comparison.json',)


def require(condition: bool, message: str) -> None:
    """Raise a readable contract failure; e.g. require(False, 'Missing task')."""
    if not condition:
        raise AssertionError(message)


def unique_ids(entries: list[dict], name: str) -> set[str]:
    """Index declared IDs without hiding duplicates; repeated R1 records fail."""
    ids = {entry['id'] for entry in entries}
    require(len(ids) == len(entries), f'Duplicate {name} ID')
    return ids


def same_typed_value(actual: object, expected: object) -> bool:
    """Compare JSON result values without coercion; 1 differs from True and 1.0.

    Lists compare recursively and dictionaries compare values under their JSON
    string keys, preserving nulls and named results such as 'overflow'.
    """
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            same_typed_value(left, right) for left, right in zip(actual, expected)
        )
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            same_typed_value(actual[key], expected[key]) for key in actual
        )
    return actual == expected


@dataclass
class ValidationContext:
    """Keep inputs and reports local; e.g. ValidationContext(Path('/repo'))."""

    root: Path
    results: list[dict[str, object]] = field(default_factory=list)

    def load(self, name: str) -> dict:
        """Read JSON beneath the root; e.g. context.load('spec/bets.json')."""
        return json.loads((self.root / name).read_text(encoding='utf-8'))

    def record(self, name: str, detail: str, count: int | None = None) -> None:
        """Append a check result; e.g. context.record('tasks', 'Pass', 10)."""
        row: dict[str, object] = {'check': name, 'status': 'pass', 'detail': detail}
        if count is not None:
            row['count'] = count
        self.results.append(row)

    def markdown_paths(self) -> list[Path]:
        """Enumerate design files and README, without traversing build outputs."""
        return [self.root / 'README.md'] + [
            self.root / 'docs' / name for name in DESIGN_DOCUMENTS
        ]

    def json_paths(self) -> list[Path]:
        """Enumerate source JSON inputs; the generated validation report stays separate."""
        return sorted((self.root / 'spec').glob('*.json')) + [
            self.root / 'docs' / name for name in DOCUMENT_REPORTS
        ]

    def load_generator(self, name: str) -> ModuleType:
        """Load a local generator; e.g. context.load_generator('generate_bets.py')."""
        path = self.root / 'tools' / name
        spec = importlib.util.spec_from_file_location(name[:-3], path)
        require(spec is not None and spec.loader is not None, str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
