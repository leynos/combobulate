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
BINDING_FIELDS = (
    'executable_digest', 'specification_digest', 'source_revision', 'target', 'features',
    'semantic_policy', 'backend_profile', 'implementation_relation',
)


class Level(enum.Enum):
    """Admission levels, strongest first; only proof, bounded, and tested can satisfy a component."""

    PROOF = 'proof'
    BOUNDED = 'bounded'
    TESTED = 'tested'
    RESTRICTED = 'restricted'
    REJECTED = 'rejected'


LEVEL_RANK = {Level.PROOF: 4, Level.BOUNDED: 3, Level.TESTED: 2, Level.RESTRICTED: 1, Level.REJECTED: 0}
EXCEPTION_PROBLEM_STATES = {
    frozenset(): None,
    frozenset({'past-release-gate'}): 'expired',
}


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


@dataclass(frozen=True, slots=True)
class VerifiedLogResult:
    """Facts re-derived by a parser from the exact log named by one record.

    An adapter creates this value only after reading the log, verifying its
    digest, and deriving every admission-relevant result from its contents.
    The pure gate also checks that these facts match the submitted record.
    """

    tool: str
    log_path: str
    log_sha256: str
    outcome: str
    bounds: str
    witness_statuses: tuple[str, ...]
    negative_controls: tuple[tuple[bool, str], ...]
    run_mode: str

    def matches_record(self, record: Mapping[str, object]) -> bool:
        """Confirm the parser-derived admission facts agree with the record."""
        method = record['method']
        bounds = record['bounds']
        witnesses = tuple(str(item['status']) for item in record['success_witnesses'])
        controls = tuple((bool(item['required']), str(item['observed'])) for item in record['negative_controls'])
        return (self.outcome == record['outcome'] and self.bounds == bounds['kind']
                and self.witness_statuses == witnesses and self.negative_controls == controls
                and self.run_mode == method['run_mode'])


@dataclass(frozen=True, slots=True)
class AdmissionContext:
    """Carry caller-owned inputs used only while abstracting one evidence record."""

    exceptions: Mapping[str, Mapping[str, object]]
    bindings: Mapping[str, Mapping[str, object]]
    as_of: datetime.date
    log_parsers: frozenset[str] = frozenset()
    verified_log_results: tuple[VerifiedLogResult, ...] = ()


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
    reasons = (
        (state.kind in EXECUTED and state.outcome != 'verified', f'outcome-{state.outcome}'),
        (state.witness != 'all-satisfied', f'witness-{state.witness}'),
        (state.controls != 'all-required-rejected-as-intended', f'control-{state.controls}'),
        (state.kind in VERIFIERS and state.trust in {'audited-uncovered', 'unaudited'},
         {'audited-uncovered': 'trust-uncovered', 'unaudited': 'trust-unaudited'}.get(state.trust, '')),
        (state.exception in {'expired', 'not-yet-valid', 'malformed'}, f'exception-{state.exception}'),
        (state.binding != 'current', f'binding-{state.binding}'),
        (state.run_mode == 'focused', 'run-focused'),
        (state.kind in VERIFIERS and state.verdict_source == 'self-reported', 'verdict-self-reported'),
        (state.kind == 'none', 'not-run'),
        (state.kind == 'trust-declaration' and state.exception != 'active', 'trust-without-exception'),
    )
    return tuple(reason for applies, reason in reasons if applies)


def base_level(state: AbstractRecord) -> Level:
    """MS-2 without exceptions: bounded evidence with partial bounds is only `bounded`."""
    if state.kind == 'deductive':
        return Level.PROOF
    if state.kind == 'bounded':
        return Level.PROOF if state.bounds == 'type-complete' else Level.BOUNDED
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
    """Classify an exception under D02; a passed release gate expires it immediately."""
    if exception is None:
        return 'none'
    problem_state = EXCEPTION_PROBLEM_STATES.get(frozenset(exception.get('problems', [])), 'malformed')
    if problem_state is not None:
        return problem_state
    approved = datetime.date.fromisoformat(str(exception['approved_on']))
    invalid_from = datetime.date.fromisoformat(str(exception['invalid_from']))
    if as_of < approved:
        return 'not-yet-valid'
    return 'active' if as_of < invalid_from else 'expired'


def trust_state(audit: Mapping[str, object], covers: frozenset[str]) -> str:
    """Abstract an audit; every covered item must name a declared assumption or exception."""
    if audit['status'] == 'unaudited':
        return 'unaudited'
    items = audit['items']
    if not items:
        return 'audited-none'
    return 'audited-all-covered' if all(item['covered_by'] in covers for item in items) else 'audited-uncovered'


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


def binding_state(record: Mapping[str, object], bindings: Mapping[str, Mapping[str, object]]) -> str:
    """Compare every schema-defined binding field with the registered current profile."""
    binding = record['binding']
    if any(binding[key] is None for key in ('executable_digest', 'specification_digest', 'source_revision')):
        return 'incomplete'
    current = bindings.get(str(record['component']))
    expected = {key: binding[key] for key in BINDING_FIELDS}
    return 'current' if current == expected else 'stale'


def _matching_verified_log_result(
    record: Mapping[str, object], context: AdmissionContext,
) -> VerifiedLogResult | None:
    """Find a registered adapter result bound to this record and its derived facts."""
    method = record['method']
    source = record['verdict_source']
    log = source['log']
    tool = str(method['tool'])
    if source['kind'] != 'log-parser':
        return None
    if log is None:
        return None
    if tool not in context.log_parsers:
        return None
    identity = (tool, str(log['path']), str(log['sha256']))
    candidates = [result for result in context.verified_log_results
                  if (result.tool, result.log_path, result.log_sha256) == identity]
    if len(candidates) != 1:
        return None
    if not candidates[0].matches_record(record):
        return None
    return candidates[0]


def _exception_for_record(record: Mapping[str, object], context: AdmissionContext) -> str:
    """Resolve one exception claim, rejecting unknown or cross-component identifiers."""
    exception_id = record['exception']
    if exception_id is None:
        return 'none'
    entry = context.exceptions.get(str(exception_id))
    if entry is None or entry.get('component') != record['component']:
        return 'malformed'
    return exception_state(entry, context.as_of)


def _trust_coverage(record: Mapping[str, object]) -> frozenset[str]:
    """Collect the assumption and exception identifiers that may cover audited items."""
    covers = {str(item) for item in record['declared_assumptions']}
    exception_id = record['exception']
    if exception_id is not None:
        covers.add(str(exception_id))
    return frozenset(covers)


def abstract_record(record: Mapping[str, object], context: AdmissionContext) -> AbstractRecord:
    """Map a schema-valid record to the abstract model; validate against the schema first.

    A verdict counts as parsed only when a registered adapter supplies a
    matching result for the named log and digest; tool registration alone is
    insufficient (C-EP-10). An unknown exception identifier is malformed.

    Parameters
    ----------
    record
        An evidence record already validated against proof-evidence schema
        version 2; this function does not validate serialized inputs.
    context
        Explicit exception, binding, date, and verified parser-result inputs.

    Returns
    -------
    AbstractRecord
        The finite admission facts; for example, an unregistered parser claim
        maps to ``verdict_source='self-reported'``.
    """
    method = record['method']
    parsed = _matching_verified_log_result(record, context) is not None
    exception = _exception_for_record(record, context)
    return AbstractRecord(
        kind=str(record['evidence_kind']), outcome=str(record['outcome']), bounds=str(record['bounds']['kind']),
        witness=witness_state(record['success_witnesses']), controls=controls_state(record['negative_controls']),
        trust=trust_state(record['trust_audit'], _trust_coverage(record)), exception=exception,
        binding=binding_state(record, context.bindings),
        run_mode=str(method['run_mode']), verdict_source='log-parser' if parsed else 'self-reported',
    )
