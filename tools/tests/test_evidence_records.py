"""Prove concrete evidence records map onto the abstract model and agree with the schema (VO-2)."""
from __future__ import annotations

import itertools
import sys
import unittest
from dataclasses import fields
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hypothesis import given, settings, strategies as st

from docs_validation import evidence_gate as gate
from docs_validation.evidence_gate import AdmissionContext, AbstractRecord, abstract_record, is_valid
from evidence_fixtures import AS_OF, BINDINGS, DIGEST, PARSERS, VALID, VALIDATOR, concrete, round_trip


def concrete_mapping_failure(state: AbstractRecord) -> str | None:
    """Return the schema or abstraction mismatch for one generated state."""
    record, exceptions = concrete(state)
    schema_valid = VALIDATOR.is_valid(record)
    expected_valid = is_valid(state)
    if schema_valid != expected_valid:
        return f'{state}: schema validity was {schema_valid}'
    if not expected_valid:
        return None
    context = AdmissionContext(exceptions=exceptions, bindings=BINDINGS,
                               as_of=AS_OF, log_parsers=PARSERS)
    actual = abstract_record(record, context)
    return f'{state}: abstraction returned {actual}' if actual != state else None


class ConcreteMapping(unittest.TestCase):
    """Every valid abstract state has a concrete record that abstracts back to it."""

    def test_schema_agrees_and_every_valid_state_round_trips_exhaustively(self):
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
        kinds = {state.kind for state in VALID}
        outcomes = {state.outcome for state in VALID}
        self.assertEqual(kinds, set(gate.KINDS), 'every evidence kind must be generated')
        self.assertEqual(outcomes, set(gate.OUTCOMES), 'every outcome must be generated')

    def test_schema_agrees_with_the_validity_predicate(self):
        base = VALID[0]
        for kind, outcome, bounds in itertools.product(gate.KINDS, gate.OUTCOMES, gate.BOUNDS):
            state = AbstractRecord(kind, outcome, bounds, *[getattr(base, item.name) for item in fields(AbstractRecord)][3:])
            record, _ = concrete(state)
            with self.subTest(kind=kind, outcome=outcome, bounds=bounds):
                self.assertEqual(VALIDATOR.is_valid(record), is_valid(state), 'schema and predicate must agree')

    @settings(max_examples=150, derandomize=True, deadline=None)
    @given(st.sampled_from(VALID))
    def test_sampled_records_are_schema_valid(self, state):
        record, _ = concrete(state)
        self.assertTrue(VALIDATOR.is_valid(record), f'the record for {state} must be schema-valid')

    @settings(max_examples=150, derandomize=True, deadline=None)
    @given(st.sampled_from(VALID), st.text(min_size=1, max_size=20), st.dates(), st.lists(st.text(min_size=1), max_size=3))
    def test_abstraction_ignores_undocumented_fields(self, state, text, date, assumptions):
        record, exceptions = concrete(state)
        record.update(claim=text, outcome_detail=text, recorded_on=date.isoformat(), declared_assumptions=assumptions)
        record['method'].update(version=text, command=text, solver=text)
        context = AdmissionContext(exceptions=exceptions, bindings=BINDINGS, as_of=AS_OF, log_parsers=PARSERS)
        self.assertEqual(abstract_record(record, context), state,
                         'fields outside the admission contract must not affect the abstraction')

    def test_every_current_binding_profile_field_affects_admission(self):
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
            context = AdmissionContext(exceptions=exceptions, bindings=BINDINGS, as_of=AS_OF,
                                       log_parsers=PARSERS)
            with self.subTest(field=field):
                self.assertEqual(abstract_record(record, context).binding, 'stale',
                                 f'a changed {field} must invalidate the current binding')

    def test_partial_current_binding_registration_fails_closed(self):
        state = next(item for item in VALID if item.binding == 'current')
        record, exceptions = concrete(state)
        incomplete = {record['component']: {'executable_digest': DIGEST}}
        context = AdmissionContext(exceptions=exceptions, bindings=incomplete, as_of=AS_OF,
                                   log_parsers=PARSERS)
        self.assertEqual(abstract_record(record, context).binding, 'stale',
                         'a partial registration cannot match the complete schema binding')

    def test_unregistered_parser_makes_the_verdict_self_reported(self):
        state = next(item for item in VALID if item.verdict_source == 'log-parser')
        record, exceptions = concrete(state)
        context = AdmissionContext(exceptions=exceptions, bindings=BINDINGS, as_of=AS_OF)
        self.assertEqual(abstract_record(record, context).verdict_source, 'self-reported',
                         'without a registered parser a verdict is self-reported (C-EP-10)')

    def test_seeded_mapping_fault_fails_the_round_trip(self):
        def faulty(controls):
            return 'all-required-rejected-as-intended'
        with patch.object(gate, 'controls_state', faulty):
            self.assertTrue(any(round_trip(state) != state for state in VALID[:2000]),
                            'a mapping that ignores negative controls must break the round trip')


if __name__ == '__main__':
    unittest.main()
