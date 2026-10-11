"""Admit proof-evidence records at the level they have earned (ADR-0009, task 1.1.4).

The gate is pure: `abstract_record` maps a schema-valid evidence record, the
exception register, the current bindings, and an injected date to a ten-field
abstract record, and `admit` maps that record to an admission level and reason
codes by the ordered rule table MS-0 to MS-2. It never reads the clock, the
environment, or the network. A record whose verdict is not re-derived by a
registered log parser is self-reported and cannot reach `proof` or `bounded`
(C-EP-10). `tools/tests/fixtures/evidence_gate_rules.json` restates the rules
as data, and the tests enumerate every abstract state against both.
"""
from __future__ import annotations

import datetime
import enum
import itertools
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, fields

KINDS = ('deductive', 'bounded', 'test', 'trust-declaration', 'none')
OUTCOMES = ('verified', 'counterexample', 'resource-exhausted', 'solver-unknown', 'unsupported', 'skipped',
            'not-run', 'tool-error')
BOUNDS = ('not-applicable', 'type-complete', 'partial')
WITNESSES = ('all-satisfied', 'some-unsatisfied', 'absent')
CONTROLS = ('all-required-rejected-as-intended', 'some-rejected-otherwise', 'some-accepted', 'required-missing')
TRUST = ('audited-none', 'audited-all-covered', 'audited-uncovered', 'unaudited')
EXCEPTIONS = ('none', 'active', 'expired', 'not-yet-valid', 'malformed')
BINDINGS = ('current', 'stale', 'incomplete')
RUN_MODES = ('full-profile', 'focused')
VERDICT_SOURCES = ('log-parser', 'self-reported')
EXECUTED = frozenset({'deductive', 'bounded', 'test'})
VERIFIERS = frozenset({'deductive', 'bounded'})


class Level(enum.Enum):
    """Admission levels, strongest first; only proof, bounded, and tested can satisfy a component."""

    PROOF = 'proof'
    BOUNDED = 'bounded'
    TESTED = 'tested'
    RESTRICTED = 'restricted'
    REJECTED = 'rejected'


LEVEL_RANK = {Level.PROOF: 4, Level.BOUNDED: 3, Level.TESTED: 2, Level.RESTRICTED: 1, Level.REJECTED: 0}


@dataclass(frozen=True)
class AbstractRecord:
    """The ten facts the gate decides on; e.g. AbstractRecord('test', 'verified', 'not-applicable', ...)."""

    kind: str
    outcome: str
    bounds: str
    witness: str
    controls: str
    trust: str
    exception: str
    binding: str
    run_mode: str
    verdict_source: str


@dataclass(frozen=True)
class Admission:
    """A level and its reason codes; blocking reasons always mean `rejected`."""

    level: Level
    reasons: tuple[str, ...]


DOMAINS = (KINDS, OUTCOMES, BOUNDS, WITNESSES, CONTROLS, TRUST, EXCEPTIONS, BINDINGS, RUN_MODES, VERDICT_SOURCES)


def all_states() -> Iterator[AbstractRecord]:
    """Enumerate the full product domain (345,600 states), valid or not."""
    return (AbstractRecord(*values) for values in itertools.product(*DOMAINS))


def is_valid(state: AbstractRecord) -> bool:
    """MS-0: nothing ran exactly for `none` and trust declarations; only bounded evidence has bounds."""
    ran = state.kind in EXECUTED
    return (state.outcome != 'not-run') == ran and (state.bounds != 'not-applicable') == (state.kind == 'bounded')


def blocking_reasons(state: AbstractRecord) -> tuple[str, ...]:
    """MS-1: one reason code per failed condition, in field order."""
    reasons: list[str] = []
    if state.kind in EXECUTED and state.outcome != 'verified':
        reasons.append(f'outcome-{state.outcome}')
    if state.witness != 'all-satisfied':
        reasons.append(f'witness-{state.witness}')
    if state.controls != 'all-required-rejected-as-intended':
        reasons.append(f'control-{state.controls}')
    if state.kind in VERIFIERS and state.trust in {'audited-uncovered', 'unaudited'}:
        reasons.append('trust-uncovered' if state.trust == 'audited-uncovered' else 'trust-unaudited')
    if state.exception in {'expired', 'not-yet-valid', 'malformed'}:
        reasons.append(f'exception-{state.exception}')
    if state.binding != 'current':
        reasons.append(f'binding-{state.binding}')
    if state.run_mode == 'focused':
        reasons.append('run-focused')
    if state.kind in VERIFIERS and state.verdict_source == 'self-reported':
        reasons.append('verdict-self-reported')
    if state.kind == 'none':
        reasons.append('not-run')
    if state.kind == 'trust-declaration' and state.exception != 'active':
        reasons.append('trust-without-exception')
    return tuple(reasons)


def base_level(state: AbstractRecord) -> Level:
    """MS-2 without exceptions: bounded evidence with partial bounds is only `bounded`."""
    if state.kind == 'deductive' or (state.kind == 'bounded' and state.bounds == 'type-complete'):
        return Level.PROOF
    if state.kind == 'bounded':
        return Level.BOUNDED
    return Level.TESTED if state.kind == 'test' else Level.RESTRICTED


def admit(state: AbstractRecord) -> Admission:
    """Admit one abstract record; pure and total over the product domain."""
    if not is_valid(state):
        return Admission(Level.REJECTED, ('schema-invalid',))
    reasons = blocking_reasons(state)
    if reasons:
        return Admission(Level.REJECTED, reasons)
    if state.exception == 'active':
        return Admission(Level.RESTRICTED, ('exception-active',))
    return Admission(base_level(state), ())


def field_names() -> tuple[str, ...]:
    """Name the abstract fields in order."""
    return tuple(item.name for item in fields(AbstractRecord))


def exception_state(exception: Mapping[str, object] | None, as_of: datetime.date) -> str:
    """Classify an exception for a date (D02): valid from approval until `invalid_from`, at most 90 days."""
    if exception is None:
        return 'none'
    if exception.get('problems'):
        return 'malformed'
    approved = datetime.date.fromisoformat(str(exception['approved_on']))
    invalid_from = datetime.date.fromisoformat(str(exception['invalid_from']))
    if as_of < approved:
        return 'not-yet-valid'
    return 'active' if as_of < invalid_from else 'expired'


def trust_state(audit: Mapping[str, object]) -> str:
    """Abstract a trust audit; an uncovered `assume`, `external_body`, or stub is `audited-uncovered`."""
    if audit['status'] == 'unaudited':
        return 'unaudited'
    items = audit['items']
    if not items:
        return 'audited-none'
    return 'audited-all-covered' if all(item['covered_by'] for item in items) else 'audited-uncovered'


def witness_state(witnesses: list[Mapping[str, object]]) -> str:
    """Abstract success witnesses; one unsatisfied `cover` makes the evidence vacuous for its claim."""
    statuses = {witness['status'] for witness in witnesses}
    if 'unsatisfied' in statuses:
        return 'some-unsatisfied'
    return 'all-satisfied' if statuses == {'satisfied'} else 'absent'


def controls_state(controls: list[Mapping[str, object]]) -> str:
    """Abstract negative controls; a control rejected for the wrong reason is as bad as one accepted."""
    observed = [control['observed'] for control in controls]
    if 'accepted' in observed:
        return 'some-accepted'
    if 'rejected-otherwise' in observed:
        return 'some-rejected-otherwise'
    if any(control['required'] and control['observed'] != 'rejected-as-intended' for control in controls):
        return 'required-missing'
    return 'all-required-rejected-as-intended'


def binding_state(record: Mapping[str, object], bindings: Mapping[str, Mapping[str, str]]) -> str:
    """Compare a record's executable, specification, and source identity with the current bindings."""
    binding = record['binding']
    keys = ('executable_digest', 'specification_digest', 'source_revision')
    if any(binding[key] is None for key in keys):
        return 'incomplete'
    current = bindings.get(str(record['component']))
    return 'current' if current is not None and all(current.get(key) == binding[key] for key in keys) else 'stale'


def abstract_record(record: Mapping[str, object], exceptions: Mapping[str, Mapping[str, object]],
                    bindings: Mapping[str, Mapping[str, str]], as_of: datetime.date,
                    log_parsers: frozenset[str] = frozenset()) -> AbstractRecord:
    """Map a schema-valid record to the abstract model; validate against the schema first.

    A verdict counts as parsed only when the record names a log and its tool has
    a registered log parser; otherwise it is self-reported (C-EP-10). An unknown
    exception identifier is malformed.
    """
    method = record['method']
    source = record['verdict_source']
    parsed = source['kind'] == 'log-parser' and source['log'] is not None and method['tool'] in log_parsers
    exception_id = record['exception']
    if exception_id is None:
        exception = 'none'
    else:
        entry = exceptions.get(str(exception_id))
        exception = 'malformed' if entry is None else exception_state(entry, as_of)
    return AbstractRecord(
        kind=str(record['evidence_kind']), outcome=str(record['outcome']), bounds=str(record['bounds']['kind']),
        witness=witness_state(record['success_witnesses']), controls=controls_state(record['negative_controls']),
        trust=trust_state(record['trust_audit']), exception=exception, binding=binding_state(record, bindings),
        run_mode=str(method['run_mode']), verdict_source='log-parser' if parsed else 'self-reported',
    )
