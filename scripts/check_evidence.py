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
from pathlib import Path

import cyclopts
from cyclopts import App
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

from docs_validation.evidence_gate import Level, abstract_record, admit  # noqa: E402
from docs_validation.exceptions import annotated_exceptions, ticked_tasks  # noqa: E402

RANK = {Level.PROOF: 4, Level.BOUNDED: 3, Level.TESTED: 2, Level.RESTRICTED: 1, Level.REJECTED: 0}


def load_json(path: Path) -> dict:
    """Read one JSON document."""
    return json.loads(path.read_text(encoding='utf-8'))


def report_line(path: Path, level: Level, reasons: tuple[str, ...]) -> str:
    """Format one result; e.g. 'spec/x.json: rejected [not-run]'."""
    return f"{path}: {level.value} [{', '.join(reasons)}]"


def exception_register(path: Path) -> dict[str, dict]:
    """Load exceptions with their D02 problems attached, as the gate expects."""
    sponsor = load_json(ROOT / 'spec/decisions.json')['authorities']['roles']['sponsor']
    return annotated_exceptions(load_json(path), sponsor, ticked_tasks(load_json(ROOT / 'spec/roadmap.json')))


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
    try:
        date = datetime.date.fromisoformat(as_of)
        wanted = Level(require)
    except ValueError as error:
        print(f'usage error: {error}', file=sys.stderr)
        return 2
    if not records or wanted not in {Level.PROOF, Level.BOUNDED, Level.TESTED}:
        print('usage error: give at least one record and require proof, bounded, or tested', file=sys.stderr)
        return 2
    validator = Draft202012Validator(load_json(ROOT / 'spec/proof-evidence.schema.json'),
                                     format_checker=Draft202012Validator.FORMAT_CHECKER)
    parsers = frozenset(load_json(log_parsers)['registered_log_parsers'])
    register, current = exception_register(exceptions), load_json(bindings)
    status, invalid = 0, False
    for path in records:
        try:
            record = load_json(path)
        except (OSError, ValueError) as error:
            print(f'{path}: unreadable: {error}', file=sys.stderr)
            invalid = True
            continue
        errors = sorted(validator.iter_errors(record), key=lambda error: list(error.path))
        if errors:
            print(f'{path}: schema-invalid: {errors[0].message}', file=sys.stderr)
            invalid = True
            continue
        admission = admit(abstract_record(record, register, current, date, parsers))
        print(report_line(path, admission.level, admission.reasons))
        if RANK[admission.level] < RANK[wanted]:
            status = 1
    return 2 if invalid else status


if __name__ == '__main__':
    app()
