#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["cyclopts==5.2.0", "jsonschema>=4,<5"]
# ///
"""Admit proof-evidence records through the evidence gate and report their levels.

Each record is validated against `spec/proof-evidence.schema.json` (schema
version 2) and then admitted by the gate in `tools/docs_validation/` on the
date given by ``--as-of``; the wall clock is never read. Exit codes: 0 when every
record reaches ``--require`` (default `tested`), 1 when any falls short, and 2
for a schema-invalid record or a usage error. Exceptions come from
`spec/exceptions.json`, current bindings from `spec/evidence-bindings.json`, and
registered log parsers from `spec/evidence-reason-codes.json`; until a parser is
registered for a verifier, its records are self-reported and cannot reach
`proof` or `bounded` (ADR-0009).
"""
from __future__ import annotations

import datetime
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cyclopts
from cyclopts import App
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))


@dataclass(frozen=True)
class EvidenceCliConfiguration:
    """Inputs shared by one CLI invocation and its per-record evaluator."""

    validator: Draft202012Validator
    parsers: frozenset[str]
    exceptions: dict[str, dict]
    bindings: dict[str, dict]
    as_of: datetime.date
    required_level: str


def load_json(path: Path) -> dict:
    """Read one JSON document."""
    return json.loads(path.read_text(encoding='utf-8'))


def report_line(path: Path, level: str, reasons: tuple[str, ...]) -> str:
    """Format one result; e.g. 'spec/x.json: rejected [not-run]'."""
    return f"{path}: {level} [{', '.join(reasons)}]"


def exception_register(path: Path) -> dict[str, dict]:
    """Load exceptions with their D02 problems attached, as the gate expects."""
    from docs_validation.exceptions import annotated_exceptions, ticked_tasks

    sponsor = load_json(ROOT / 'spec/decisions.json')['authorities']['roles']['sponsor']
    return annotated_exceptions(load_json(path), sponsor, ticked_tasks(load_json(ROOT / 'spec/roadmap.json')))


def evaluate_record(path: Path, configuration: EvidenceCliConfiguration) -> tuple[int, bool]:
    """Validate one input against the immutable settings for this CLI invocation."""
    from docs_validation.evidence_gate import LEVEL_RANK, Level, abstract_record, admit

    try:
        record = load_json(path)
    except (OSError, ValueError) as error:
        print(f'{path}: unreadable: {error}', file=sys.stderr)
        return 0, True
    errors = sorted(configuration.validator.iter_errors(record), key=lambda error: list(error.path))
    if errors:
        print(f'{path}: schema-invalid: {errors[0].message}', file=sys.stderr)
        return 0, True
    abstract = abstract_record(record, configuration.exceptions, configuration.bindings,
                               configuration.as_of, configuration.parsers)
    admission = admit(abstract)
    print(report_line(path, admission.level.value, admission.reasons))
    required = Level(configuration.required_level)
    return int(LEVEL_RANK[admission.level] < LEVEL_RANK[required]), False


app = App(help=__doc__.splitlines()[0], config=cyclopts.config.Env('INPUT_', command=False))


@app.default
def main(*records: Path, as_of: str, require: str = 'tested', bindings: Path = ROOT / 'spec/evidence-bindings.json',
         log_parsers: Path = ROOT / 'spec/evidence-reason-codes.json',
         exceptions: Path = ROOT / 'spec/exceptions.json') -> int:
    """Admit each record and compare its level with the requirement; e.g. a planned record exits 1.

    Parameters
    ----------
    records
        Evidence record files to admit.
    as_of
        Evaluation date, YYYY-MM-DD; it decides exception validity.
    require
        Minimum level for success: proof, bounded, or tested.
    bindings
        JSON map from component to its current executable, specification, and source identity.
    log_parsers
        JSON document whose `registered_log_parsers` lists tools with registered log parsers.
    exceptions
        The exception register.
    """
    from docs_validation.evidence_gate import Level

    try:
        date = datetime.date.fromisoformat(as_of)
        wanted = Level(require)
    except ValueError as error:
        print(f'usage error: {error}', file=sys.stderr)
        return 2
    if not records or wanted not in {Level.PROOF, Level.BOUNDED, Level.TESTED}:
        print('usage error: give at least one record and require proof, bounded, or tested', file=sys.stderr)
        return 2
    try:
        validator = Draft202012Validator(load_json(ROOT / 'spec/proof-evidence.schema.json'),
                                         format_checker=Draft202012Validator.FORMAT_CHECKER)
        parsers = frozenset(load_json(log_parsers)['registered_log_parsers'])
        register, current = exception_register(exceptions), load_json(bindings)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'usage error: cannot load configuration: {error}', file=sys.stderr)
        return 2
    configuration = EvidenceCliConfiguration(validator, parsers, register, current, date, wanted.value)

    status, invalid = 0, False
    for path in records:
        record_status, record_invalid = evaluate_record(path, configuration)
        status = max(status, record_status)
        invalid = invalid or record_invalid
    return 2 if invalid else status


if __name__ == '__main__':
    app()
