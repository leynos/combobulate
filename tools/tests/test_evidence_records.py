"""Prove concrete evidence records map onto the abstract model and agree with the schema (VO-2)."""
from __future__ import annotations

import itertools
import sys
import unittest
from dataclasses import fields, replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hypothesis import given, settings, strategies as st

from docs_validation import evidence_gate as gate
from docs_validation.evidence_gate import AdmissionContext, AbstractRecord, abstract_record, is_valid
from evidence_fixtures import (AS_OF, BINDINGS, DIGEST, PARSERS, VALID, VALIDATOR, admission_context, concrete,
                               round_trip, verified_log_results)
from markdown_examples import load_marked_json_examples

ROOT = Path(__file__).resolve().parents[2]


def concrete_mapping_failure(state: AbstractRecord) -> str | None:
    """Return the schema or abstraction mismatch for one generated state."""
    record, exceptions = concrete(state)
    schema_valid = VALIDATOR.is_valid(record)
    expected_valid = is_valid(state)
    if schema_valid != expected_valid:
        return f'{state}: schema validity was {schema_valid}'
    if not expected_valid:
        return None
    context = admission_context(record, exceptions)
    actual = abstract_record(record, context)
    return f'{state}: abstraction returned {actual}' if actual != state else None


class ConcreteMapping(unittest.TestCase):
    """Every valid abstract state has a concrete record that abstracts back to it."""

    def test_schema_agrees_and_every_valid_state_round_trips_exhaustively(self):
        """Round-trip every schema-valid abstract state through a concrete record."""
        mismatches = []
        for state in gate.all_states():
            mismatch = concrete_mapping_failure(state)
            if mismatch is not None:
                mismatches.append(mismatch)
            if len(mismatches) == 3:
                break
        self.assertEqual(mismatches, [],
                         'all 345,600 states must agree with schema validity and all valid records must round-trip')

    def test_generated_records_cover_every_kind_and_outcome(self):
        """Keep the fixture generator representative of every declared kind and outcome."""
        kinds = {state.kind for state in VALID}
        outcomes = {state.outcome for state in VALID}
        self.assertEqual(kinds, set(gate.KINDS), 'every evidence kind must be generated')
        self.assertEqual(outcomes, set(gate.OUTCOMES), 'every outcome must be generated')

    def test_schema_agrees_with_the_validity_predicate(self):
        """Compare schema validity with the complete kind, outcome, and bounds matrix."""
        base = VALID[0]
        for kind, outcome, bounds in itertools.product(gate.KINDS, gate.OUTCOMES, gate.BOUNDS):
            state = AbstractRecord(kind, outcome, bounds, *[getattr(base, item.name) for item in fields(AbstractRecord)][3:])
            record, _ = concrete(state)
            with self.subTest(kind=kind, outcome=outcome, bounds=bounds):
                self.assertEqual(VALIDATOR.is_valid(record), is_valid(state), 'schema and predicate must agree')

    @settings(max_examples=150, derandomize=True, deadline=None)
    @given(st.sampled_from(VALID))
    def test_sampled_records_are_schema_valid(self, state):
        """Keep generated valid abstract states representable by the concrete schema."""
        record, _ = concrete(state)
        self.assertTrue(VALIDATOR.is_valid(record), f'the record for {state} must be schema-valid')

    @settings(max_examples=150, derandomize=True, deadline=None)
    @given(st.sampled_from(VALID), st.text(min_size=1, max_size=20), st.dates())
    def test_abstraction_ignores_undocumented_fields(self, state, text, date):
        """Ensure fields outside the admission contract cannot change the abstraction."""
        record, exceptions = concrete(state)
        record.update(claim=text, outcome_detail=text, recorded_on=date.isoformat())
        record['method'].update(version=text, command=text, solver=text)
        context = admission_context(record, exceptions)
        self.assertEqual(abstract_record(record, context), state,
                         'fields outside the admission contract must not affect the abstraction')

    def test_every_current_binding_profile_field_affects_admission(self):
        """Reject a record when any registered binding field changes."""
        state = next(item for item in VALID if item.binding == 'current')
        alternatives = {
            'target': 'aarch64-unknown-linux-gnu',
            'features': ['different-feature'],
            'semantic_policy': 'different semantic policy',
            'backend_profile': 'different backend profile',
            'implementation_relation': 'Different implementation relation.',
        }
        for field, value in alternatives.items():
            record, exceptions = concrete(state)
            record['binding'][field] = value
            context = admission_context(record, exceptions)
            with self.subTest(field=field):
                self.assertEqual(abstract_record(record, context).binding, 'stale',
                                 f'a changed {field} must invalidate the current binding')

    def test_partial_current_binding_registration_fails_closed(self):
        """Reject a binding registration that omits fields required for comparison."""
        state = next(item for item in VALID if item.binding == 'current')
        record, exceptions = concrete(state)
        incomplete = {record['component']: {'executable_digest': DIGEST}}
        context = AdmissionContext(exceptions=exceptions, bindings=incomplete, as_of=AS_OF,
                                   log_parsers=PARSERS, verified_log_results=verified_log_results(record))
        self.assertEqual(abstract_record(record, context).binding, 'stale',
                         'a partial registration cannot match the complete schema binding')

    def test_unregistered_parser_makes_the_verdict_self_reported(self):
        """Treat a parser claim as self-reported until its tool is registered."""
        state = next(item for item in VALID if item.verdict_source == 'log-parser')
        record, exceptions = concrete(state)
        context = AdmissionContext(exceptions=exceptions, bindings=BINDINGS, as_of=AS_OF)
        self.assertEqual(abstract_record(record, context).verdict_source, 'self-reported',
                         'without a registered parser a verdict is self-reported (C-EP-10)')

    def test_registered_parser_without_verified_result_is_self_reported(self):
        """Require parser output as well as tool registration before trusting a verdict."""
        state = next(item for item in VALID if item.verdict_source == 'log-parser')
        record, exceptions = concrete(state)
        context = AdmissionContext(exceptions, BINDINGS, AS_OF, PARSERS)

        self.assertEqual(abstract_record(record, context).verdict_source, 'self-reported',
                         'a registered tool name cannot replace a verified adapter result')

    def test_verified_parser_result_must_match_log_identity_and_claims(self):
        """Reject a parser result bound to another log or inconsistent with the submitted record."""
        state = next(item for item in VALID if item.verdict_source == 'log-parser')
        record, exceptions = concrete(state)
        result = verified_log_results(record)[0]
        mismatches = (
            ('tool', replace(result, tool='other-tool')),
            ('log path', replace(result, log_path='logs/other.log')),
            ('log digest', replace(result, log_sha256='c' * 64)),
            ('outcome', replace(result, outcome='counterexample')),
            ('bounds', replace(result, bounds='partial')),
            ('witnesses', replace(result, witness_statuses=('unsatisfied',))),
            ('negative controls', replace(result, negative_controls=((True, 'accepted'),))),
            ('run mode', replace(result, run_mode='focused')),
        )
        for field, mismatch in mismatches:
            context = AdmissionContext(exceptions, BINDINGS, AS_OF, PARSERS, (mismatch,))
            with self.subTest(field=field):
                self.assertEqual(abstract_record(record, context).verdict_source, 'self-reported',
                                 f'a mismatched {field} must fail closed')

    def test_seeded_mapping_fault_fails_the_round_trip(self):
        """Show that the exhaustive round-trip detects a broken control abstraction."""
        def faulty(controls):
            """Model an incorrect mapper that ignores every negative control."""
            return 'all-required-rejected-as-intended'
        with patch.object(gate, 'controls_state', faulty):
            self.assertTrue(any(round_trip(state) != state for state in VALID[:2000]),
                            'a mapping that ignores negative controls must break the round trip')

    def test_schema_rejects_legacy_version_and_unknown_properties(self):
        """Reject version 1 and undocumented top-level fields under the version 2 contract."""
        state = next(item for item in VALID if item.kind == 'test')
        record, _ = concrete(state)

        legacy = record | {'schema_version': 1}
        unknown = record | {'undocumented_field': 'must not be accepted'}

        self.assertFalse(VALIDATOR.is_valid(legacy), 'version 1 records must not be dual-read')
        self.assertFalse(VALIDATOR.is_valid(unknown), 'unknown top-level fields must fail schema validation')

    def test_documented_schema_migration_examples_match_the_contract(self):
        """Read the migration examples from Markdown and verify the version transition."""
        examples = load_marked_json_examples(ROOT / 'docs/revision-0.2.md')
        self.assertEqual(set(examples), {'evidence-v1-fields', 'evidence-v2-fields'},
                         'the migration document must expose both marked version examples')
        self.assertEqual(examples['evidence-v1-fields'], {'schema_version': 1, 'status': 'proved'},
                         'the before example must show the retired version 1 fields')
        self.assertEqual(examples['evidence-v2-fields'], {
            'schema_version': 2, 'evidence_kind': 'deductive', 'outcome': 'verified',
        }, 'the after example must show the version 2 kind and outcome fields')
        self.assertFalse(VALIDATOR.is_valid(examples['evidence-v1-fields']),
                         'the migrated gate must reject the version 1 example')

    def test_trust_coverage_must_name_an_assumption_or_exception(self):
        """Require each audited item to resolve to an assumption or cited exception."""
        audit = {'status': 'audited', 'items': [{'covered_by': 'unregistered claim'}]}
        self.assertEqual(gate.trust_state(audit, frozenset({'declared assumption'})), 'audited-uncovered',
                         'an arbitrary non-empty coverage label must not satisfy trust audit')
        self.assertEqual(gate.trust_state(audit, frozenset({'unregistered claim'})), 'audited-all-covered',
                         'a declared assumption or cited exception may cover a trusted item')
        self.assertEqual(gate.trust_state({'status': 'audited', 'items': []}, frozenset()), 'audited-none',
                         'an empty audited trust inventory remains distinct')
        self.assertEqual(gate.trust_state({'status': 'unaudited', 'items': []}, frozenset()), 'unaudited',
                         'an unaudited record remains distinct')

        state = next(item for item in VALID if item.trust == 'audited-all-covered' and item.exception == 'none')
        record, exceptions = concrete(state)
        record['trust_audit']['items'][0]['covered_by'] = 'undeclared claim'
        context = admission_context(record, exceptions)
        self.assertEqual(abstract_record(record, context).trust, 'audited-uncovered',
                         'an arbitrary record label must not stand in for a declared assumption')

        state = AbstractRecord(
            'bounded', 'verified', 'type-complete', 'all-satisfied',
            'all-required-rejected-as-intended', 'audited-all-covered', 'active',
            'current', 'full-profile', 'log-parser',
        )
        record, exceptions = concrete(state)
        record['trust_audit']['items'][0]['covered_by'] = 'EXC-0001'
        context = admission_context(record, exceptions)
        self.assertEqual(abstract_record(record, context).trust, 'audited-all-covered',
                         'the cited component exception may cover a trusted item')

    def test_trust_coverage_projection_collects_declared_sources(self):
        """Collect declared assumptions and the optional cited exception for trust audits."""
        record = {'declared_assumptions': ['A-0001'], 'exception': 'EXC-0001'}
        self.assertEqual(gate._trust_coverage(record), frozenset({'A-0001', 'EXC-0001'}),
                         'trust coverage must include declared assumptions and the cited exception')
        record['exception'] = None
        self.assertEqual(gate._trust_coverage(record), frozenset({'A-0001'}),
                         'trust coverage must omit an absent exception without dropping assumptions')

    def test_exception_for_another_component_is_malformed(self):
        """Reject a cited exception whose authority narrows a different component."""
        state = AbstractRecord(
            'trust-declaration', 'not-run', 'not-applicable', 'all-satisfied',
            'all-required-rejected-as-intended', 'audited-none', 'active', 'current',
            'full-profile', 'self-reported',
        )
        record, exceptions = concrete(state)
        exceptions['EXC-0001']['component'] = 'PF01.proof@1.2.4'
        context = admission_context(record, exceptions)

        admission = gate.admit(abstract_record(record, context))

        self.assertEqual(admission.level, gate.Level.REJECTED,
                         'an exception cannot narrow a different proof component')
        self.assertEqual(admission.reasons, ('exception-malformed', 'trust-without-exception'),
                         'a mismatched exception is malformed and cannot authorize a trust declaration')


if __name__ == '__main__':
    unittest.main()
