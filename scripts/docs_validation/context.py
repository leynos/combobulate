"""Own explicit design-pack inputs and validation reporting.

Feature checks accept one context, so tests can supply an isolated repository
without changing process globals. Only the checker composition root writes reports.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import ModuleType

import yaml

DESIGN_DOCUMENTS = (
    'acceptance-calibration.md', 'context.md', 'decision-register.md', 'evidence-and-decision-records.md', 'language-reference.md', 'references.md', 'revision-0.2.md',
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
    """Keep inputs and reports local; e.g. ValidationContext(Path('/repo'), as_of=date(2026, 10, 11)).

    ``as_of`` is injected by the caller (``make design-check`` passes the HEAD
    commit date) so date-dependent checks never read the wall clock.
    ``source_revision`` identifies the checked-out commit for evidence bound to
    this validation run.
    """

    root: Path
    results: list[dict[str, object]] = field(default_factory=list)
    as_of: date | None = None
    source_revision: str | None = None

    def load(self, name: str) -> dict:
        """Read JSON beneath the root; e.g. context.load('spec/bets.json')."""
        return json.loads((self.root / name).read_text(encoding='utf-8'))

    def load_yaml(self, name: str) -> object:
        """Parse YAML beneath the root; e.g. load the CI workflow as source data."""
        try:
            return yaml.safe_load((self.root / name).read_text(encoding='utf-8'))
        except yaml.YAMLError as error:
            raise ValueError(f'Invalid YAML in {name}: {error}') from error

    def read_bytes(self, name: str) -> bytes:
        """Read raw source bytes; e.g. hash a registered workload file."""
        return (self.root / name).read_bytes()

    def record(self, name: str, detail: str, count: int | None = None) -> None:
        """Append a check result; e.g. context.record('tasks', 'Pass', 10)."""
        row: dict[str, object] = {'check': name, 'status': 'pass', 'detail': detail}
        if count is not None:
            row['count'] = count
        self.results.append(row)

    def markdown_paths(self) -> list[Path]:
        """Enumerate design files, ADRs, and README without traversing build outputs.

        From the repository root, ADR files under `docs/adrs/` are included::

            >>> context = ValidationContext(Path.cwd())
            >>> any(path.parent.name == 'adrs' for path in context.markdown_paths())
            True
        """
        return [self.root / 'README.md'] + [
            self.root / 'docs' / name for name in DESIGN_DOCUMENTS
        ] + sorted((self.root / 'docs' / 'adrs').glob('adr-*.md'))

    def json_paths(self) -> list[Path]:
        """Enumerate source JSON inputs; the generated validation report stays separate."""
        return sorted((self.root / 'spec').glob('*.json')) + [
            self.root / 'docs' / name for name in DOCUMENT_REPORTS
        ]

    def load_generator(self, name: str) -> ModuleType:
        """Load a local generator; e.g. context.load_generator('generate_bets.py')."""
        return self.load_module(self.root / 'scripts' / name)

    def load_script(self, name: str) -> ModuleType:
        """Load a helper script's functions; e.g. context.load_script('export_roadmap.py').

        Parameters
        ----------
        name
            Filename of the helper script beneath the repository's
            `scripts/` directory.

        Returns
        -------
        ModuleType
            Imported module containing the helper script's functions.
        """
        return self.load_module(self.root / 'scripts' / name)

    @staticmethod
    def load_module(path: Path) -> ModuleType:
        """Import a Python file by path without running its command-line entry point.

        The module is registered under a checker-private name during execution,
        because decorators such as `dataclass` resolve the defining module
        through that table. Any prior registry entry is restored afterwards.

        Parameters
        ----------
        path
            Filesystem path to the Python source file to import.

        Returns
        -------
        ModuleType
            The imported module.

        Examples
        --------
        Load the roadmap exporter without invoking its command-line entry point:

        >>> module = ValidationContext.load_module(
        ...     Path('scripts/export_roadmap.py'))
        >>> module.__name__
        '_design_pack_scripts_export_roadmap'
        """
        name = f'_design_pack_{path.parent.name}_{path.stem}'
        spec = importlib.util.spec_from_file_location(name, path)
        require(spec is not None and spec.loader is not None, str(path))
        module = importlib.util.module_from_spec(spec)
        previous_module = sys.modules.get(name)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            if previous_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous_module
        return module
