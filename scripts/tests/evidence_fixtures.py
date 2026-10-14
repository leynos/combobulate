"""Build concrete evidence records that denote given abstract states, for the evidence-gate suites."""
from __future__ import annotations

import copy
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonschema import Draft202012Validator

from docs_validation.context import ValidationContext
from docs_validation.evidence_gate import AbstractRecord, abstract_record, all_states, is_valid

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = ValidationContext(ROOT)
VALIDATOR = Draft202012Validator(CONTEXT.load('spec/proof-evidence.schema.json'),
                                 format_checker=Draft202012Validator.FORMAT_CHECKER)
TEMPLATE = CONTEXT.load('spec/proof-evidence.example.json')
AS_OF = datetime.date(2026, 10, 11)
DIGEST = 'a' * 64
REVISION = 'b' * 40
BINDINGS = {TEMPLATE['component']: {'executable_digest': DIGEST, 'specification_digest': DIGEST,
                                    'source_revision': REVISION}}
PARSERS = frozenset({'kani'})
EXCEPTION_DATES = {'active': ('2026-10-01', '2026-11-01'), 'expired': ('2026-08-01', '2026-10-01'),
                   'not-yet-valid': ('2026-10-20', '2026-11-20')}
WITNESSES = {'all-satisfied': ['satisfied'], 'some-unsatisfied': ['satisfied', 'unsatisfied'], 'absent': ['not-observed']}
CONTROLS = {'all-required-rejected-as-intended': [(True, 'rejected-as-intended'), (False, 'not-run')],
            'some-rejected-otherwise': [(True, 'rejected-otherwise')], 'some-accepted': [(True, 'accepted')],
            'required-missing': [(True, 'not-run')]}
TRUST = {'audited-none': ('audited', []), 'audited-all-covered': ('audited', ['A1']),
         'audited-uncovered': ('audited', [None]), 'unaudited': ('unaudited', [])}


def concrete(state: AbstractRecord) -> tuple[dict, dict]:
    """Build a concrete record and exception register that denote one abstract state."""
    record = copy.deepcopy(TEMPLATE)
    record.update(evidence_kind=state.kind, outcome=state.outcome, bounds={'kind': state.bounds, 'statement': 'Scope.'})
    record['success_witnesses'] = [{'id': f'w{index}', 'description': 'Witness.', 'status': status}
                                   for index, status in enumerate(WITNESSES[state.witness])]
    record['negative_controls'] = [{'id': f'c{index}', 'required': required, 'expected_failure': 'Fails.',
                                    'observed': observed} for index, (required, observed) in enumerate(CONTROLS[state.controls])]
    status, covers = TRUST[state.trust]
    record['trust_audit'] = {'status': status, 'items': [{'item': 'assume', 'location': 'src/lib.rs:1', 'covered_by': cover}
                                                         for cover in covers]}
    executable = None if state.binding == 'incomplete' else (DIGEST if state.binding == 'current' else 'c' * 64)
    record['binding'].update(executable_digest=executable, specification_digest=DIGEST, source_revision=REVISION)
    record['method'].update(tool='kani', run_mode=state.run_mode)
    record['verdict_source'] = ({'kind': 'log-parser', 'log': {'path': 'logs/run.log', 'sha256': DIGEST}}
                                if state.verdict_source == 'log-parser' else {'kind': 'self-reported', 'log': None})
    exceptions: dict = {}
    if state.exception == 'none':
        record['exception'] = None
    elif state.exception == 'malformed':
        record['exception'] = 'EXC-9999'
    else:
        record['exception'] = 'EXC-0001'
        approved, invalid_from = EXCEPTION_DATES[state.exception]
        exceptions['EXC-0001'] = {'approved_on': approved, 'invalid_from': invalid_from, 'problems': []}
    return record, exceptions


def round_trip(state: AbstractRecord) -> AbstractRecord:
    """Abstract the concrete record built for a state."""
    record, exceptions = concrete(state)
    return abstract_record(record, exceptions, BINDINGS, AS_OF, PARSERS)


VALID = [state for state in all_states() if is_valid(state)]
