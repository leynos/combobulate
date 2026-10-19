#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["cyclopts==5.2.0", "jsonschema>=4,<5", "PyYAML==6.0.3"]
# ///
"""Admit proof-evidence records through the evidence gate and report their levels.

Each record is validated against `spec/proof-evidence.schema.json` (schema
version 2) and then admitted by the gate in `tools/docs_validation/` on the
date given by ``--as-of``; the wall clock is never read. Exit codes: 0 when every
record reaches ``--require`` (default `tested`), 1 when any falls short, and 2
for a schema-invalid record or a usage error. Exceptions come from
`spec/exceptions.json` and current bindings from
`spec/evidence-bindings.json`. Verifier records stay self-reported until a
registered parser adapter supplies a digest-bound result to the gate; tool
registration alone cannot admit them (ADR-0009). No parser adapter is
integrated into this command yet, so verifier records cannot reach `proof` or
`bounded` through the CLI.
"""
from __future__ import annotations

import datetime
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import cyclopts
from cyclopts import App, Parameter
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

if TYPE_CHECKING:
    from docs_validation.evidence_gate import AdmissionContext


@dataclass(frozen=True)
class EvidenceCliConfiguration:
    """Inputs shared by one CLI invocation and its per-record evaluator."""

    validator: Draft202012Validator
    admission_context: AdmissionContext
    required_level: str


@dataclass(frozen=True)
class EvidenceCliOptions:
    """Flat CLI option group; its fields retain the public long-option names."""

    as_of: Annotated[str, Parameter(help='Evaluation date, YYYY-MM-DD; it decides exception validity.')]
    require: Annotated[str, Parameter(help='Minimum level for success: proof, bounded, or tested.')] = 'tested'
    bindings: Annotated[
        Path, Parameter(help='JSON map from component to its complete current executable and verification profile.')
    ] = ROOT / 'spec/evidence-bindings.json'
    exceptions: Annotated[Path, Parameter(help='The exception register.')] = ROOT / 'spec/exceptions.json'
    decisions: Annotated[
        Path, Parameter(help='The decision register supplying the sponsor authority.')
    ] = ROOT / 'spec/decisions.json'
    roadmap: Annotated[
        Path, Parameter(help='The roadmap export supplying completed release gates.')
    ] = ROOT / 'spec/roadmap.json'


def load_json(path: Path) -> dict:
    """Read one JSON document; e.g. an object becomes a Python dictionary.

    Parameters
    ----------
    path
        UTF-8 JSON input file.

    Returns
    -------
    dict
        The parsed document; callers validate its required shape.

    Raises
    ------
    OSError
        If the file cannot be read.
    ValueError
        If its contents are not valid JSON or UTF-8 text.
    """
    return json.loads(path.read_text(encoding='utf-8'))


def load_bindings(path: Path) -> dict:
    """Load component profiles from a JSON object.

    For example, ``{"PF01.proof@1": {"source_revision": "..."}}`` is
    returned as a mapping; a top-level array or ``null`` raises ``ValueError``.

    Parameters
    ----------
    path
        UTF-8 JSON map of components to their current profiles.

    Returns
    -------
    dict
        The component-profile mapping.

    Raises
    ------
    OSError
        If the file cannot be read.
    ValueError
        If the document is invalid JSON, invalid UTF-8, or not an object.
    """
    bindings = load_json(path)
    if not isinstance(bindings, dict):
        raise ValueError(f'{path} must contain a JSON object mapping components to profiles')
    return bindings


def report_line(path: Path, level: str, reasons: tuple[str, ...]) -> str:
    """Format one result; e.g. 'spec/x.json: rejected [not-run]'.

    Parameters
    ----------
    path
        Input record path displayed to the caller.
    level
        Admission level to report.
    reasons
        Ordered gate reason codes.

    Returns
    -------
    str
        The path, level, and bracketed reason list on one line.
    """
    return f"{path}: {level} [{', '.join(reasons)}]"


def exception_register(path: Path, decisions: Path, roadmap: Path) -> dict[str, dict]:
    """Load exceptions with D02 problems from explicit policy inputs.

    For example, a completed release gate in ``roadmap`` attaches the
    ``past-release-gate`` problem even before an exception's expiry date.

    Parameters
    ----------
    path
        The JSON exception register.
    decisions
        The JSON decision register supplying the sponsor authority.
    roadmap
        The JSON roadmap export supplying completed release-gate tasks.

    Returns
    -------
    dict[str, dict]
        Exception entries indexed by identifier, with named problems attached.

    Raises
    ------
    OSError
        If any input cannot be read.
    ValueError
        If an input is invalid JSON, invalid UTF-8, or has an invalid date.
    KeyError, TypeError
        If policy input fields do not have the expected structure.
    """
    from docs_validation.exceptions import annotated_exceptions, ticked_tasks

    sponsor = load_json(decisions)['authorities']['roles']['sponsor']
    return annotated_exceptions(load_json(path), sponsor, ticked_tasks(load_json(roadmap)))


def evaluate_record(path: Path, configuration: EvidenceCliConfiguration) -> tuple[int, bool]:
    """Validate one input against immutable CLI settings; e.g. an invalid record returns ``(0, True)``.

    Parameters
    ----------
    path
        Evidence record to read and report.
    configuration
        Schema validator, admission inputs, and required admission level.

    Returns
    -------
    tuple[int, bool]
        The insufficient-level status and whether the record was unreadable or
        schema-invalid. Expected input failures are reported on standard error.
    """
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
    abstract = abstract_record(record, configuration.admission_context)
    admission = admit(abstract)
    print(report_line(path, admission.level.value, admission.reasons))
    required = Level(configuration.required_level)
    return int(LEVEL_RANK[admission.level] < LEVEL_RANK[required]), False


app = App(help=__doc__.splitlines()[0], config=cyclopts.config.Env('INPUT_', command=False))


@app.default
def main(
    *records: Path,
    options: Annotated[EvidenceCliOptions, Parameter(name='*')],
) -> int:
    """Admit each record and compare its level with the requirement; e.g. a planned record exits 1.

    Parameters
    ----------
    records
        Evidence record files to admit.
    options
        Flat options preserving their documented command-line names.

    Returns
    -------
    int
        Zero when all records reach the required level, one when any falls
        short, or two for invalid records, configuration, or usage.
    """
    from docs_validation.evidence_gate import AdmissionContext, Level

    try:
        date = datetime.date.fromisoformat(options.as_of)
        wanted = Level(options.require)
    except ValueError as error:
        print(f'usage error: {error}', file=sys.stderr)
        return 2
    if not records or wanted not in {Level.PROOF, Level.BOUNDED, Level.TESTED}:
        print('usage error: give at least one record and require proof, bounded, or tested', file=sys.stderr)
        return 2
    try:
        validator = Draft202012Validator(load_json(ROOT / 'spec/proof-evidence.schema.json'),
                                         format_checker=Draft202012Validator.FORMAT_CHECKER)
        register = exception_register(options.exceptions, options.decisions, options.roadmap)
        current = load_bindings(options.bindings)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'usage error: cannot load configuration: {error}', file=sys.stderr)
        return 2
    admission_context = AdmissionContext(register, current, date)
    configuration = EvidenceCliConfiguration(validator, admission_context, wanted.value)

    status, invalid = 0, False
    for path in records:
        record_status, record_invalid = evaluate_record(path, configuration)
        status = max(status, record_status)
        invalid = invalid or record_invalid
    return 2 if invalid else status


if __name__ == '__main__':
    app()
