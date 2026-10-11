"""Load proof-evidence records and run the evidence gate's structural self-check.

`check_evidence_gate` is the `evidence-gate` check that component
`PF14.structural@1.1.4` cites: it requires the gate's reason codes to match the
single-sourced registry exactly, re-checks the exception and partial-bounds
properties (P3, P4) over every valid abstract state, and admits every committed
record, including the planned example, through the schema and the gate.
`admitted_evidence` gives roadmap closure the admission of each committed
record, so a record-sourced component is satisfied only by admitted evidence.
"""
from __future__ import annotations

import datetime
import json
from collections.abc import Mapping

from jsonschema import Draft202012Validator

from .context import ValidationContext, require
from .evidence_gate import Admission, Level, abstract_record, admit, all_states, is_valid
from .exceptions import annotated_exceptions, ticked_tasks

SATISFYING = {Level.PROOF, Level.BOUNDED, Level.TESTED}


def evidence_inputs(context: ValidationContext) -> tuple[dict, dict, frozenset[str]]:
    """Load exceptions (with problems attached), current bindings, and registered log parsers."""
    sponsor = context.load('spec/decisions.json')['authorities']['roles']['sponsor']
    exceptions = annotated_exceptions(context.load('spec/exceptions.json'), sponsor,
                                      ticked_tasks(context.load('spec/roadmap.json')))
    registry = context.load('spec/evidence-reason-codes.json')
    return exceptions, context.load('spec/evidence-bindings.json'), frozenset(registry['registered_log_parsers'])


def committed_records(context: ValidationContext) -> list[tuple[str, dict]]:
    """Return every record under spec/evidence/, by repository path."""
    return [(path.relative_to(context.root).as_posix(), json.loads(path.read_text(encoding='utf-8')))
            for path in sorted((context.root / 'spec/evidence').glob('*.json'))]


def admit_record(record: Mapping[str, object], context: ValidationContext, inputs: tuple) -> Admission:
    """Admit one schema-valid record on the context's injected date; without a date, exceptions fail closed."""
    exceptions, bindings, parsers = inputs
    as_of = context.as_of
    if as_of is None:
        exceptions = {key: dict(entry) | {'problems': ['no-evaluation-date']} for key, entry in exceptions.items()}
        as_of = datetime.date.min
    return admit(abstract_record(record, exceptions, bindings, as_of, parsers))


def admitted_evidence(context: ValidationContext) -> dict[str, list[tuple[Admission, dict]]]:
    """Index committed records by component with their admissions."""
    inputs = evidence_inputs(context)
    evidence: dict[str, list[tuple[Admission, dict]]] = {}
    for _, record in committed_records(context):
        evidence.setdefault(str(record['component']), []).append((admit_record(record, context, inputs), record))
    return evidence


def check_evidence_gate(context: ValidationContext) -> None:
    """Self-check the gate against its registry and properties, then admit every committed record."""
    registry = context.load('spec/evidence-reason-codes.json')
    validator = Draft202012Validator(context.load('spec/proof-evidence.schema.json'),
                                     format_checker=Draft202012Validator.FORMAT_CHECKER)
    produced: set[str] = set()
    for state in all_states():
        admission = admit(state)
        produced.update(admission.reasons)
        if is_valid(state):
            require(state.exception == 'none' or admission.level not in SATISFYING, f'P3 fails at {state}')
            require(state.bounds != 'partial' or admission.level is not Level.PROOF, f'P4 fails at {state}')
    require(produced == set(registry['reason_codes']), 'Gate reason codes differ from spec/evidence-reason-codes.json: '
            f'{sorted(produced ^ set(registry["reason_codes"]))}')
    require([level.value for level in Level] == registry['levels'], 'Gate levels differ from the registry')
    inputs = evidence_inputs(context)
    example = context.load('spec/proof-evidence.example.json')
    records = [('spec/proof-evidence.example.json', example)] + committed_records(context)
    for path, record in records:
        validator.validate(record)
    planned = admit_record(example, context, inputs)
    require(planned.level is Level.REJECTED and 'not-run' in planned.reasons, 'The planned example must be rejected as not run')
    context.record('evidence-gate', 'Gate reason codes and levels match the registry; P3 and P4 hold over all valid '
                                    'abstract states; every committed evidence record validates against schema '
                                    'version 2, and the planned example is rejected as not run.', len(records))
