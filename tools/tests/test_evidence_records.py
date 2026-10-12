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
from docs_validation.evidence_gate import AbstractRecord, abstract_record, is_valid
from evidence_fixtures import AS_OF, BINDINGS, PARSERS, VALID, VALIDATOR, concrete, round_trip


class ConcreteMapping(unittest.TestCase):
    """Every valid abstract state has a concrete record that abstracts back to it."""

    def test_every_valid_state_round_trips(self):
        mismatches = [state for state in VALID if round_trip(state) != state]
        self.assertEqual(mismatches[:3], [], f'{len(mismatches)} states do not round-trip')

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
        record['binding'].update(target=text, semantic_policy=text)
        self.assertEqual(abstract_record(record, exceptions, BINDINGS, AS_OF, PARSERS), state,
                         'only documented fields may affect the abstraction')

    def test_unregistered_parser_makes_the_verdict_self_reported(self):
        state = next(item for item in VALID if item.verdict_source == 'log-parser')
        record, exceptions = concrete(state)
        self.assertEqual(abstract_record(record, exceptions, BINDINGS, AS_OF).verdict_source, 'self-reported',
                         'without a registered parser a verdict is self-reported (C-EP-10)')

    def test_seeded_mapping_fault_fails_the_round_trip(self):
        def faulty(controls):
            return 'all-required-rejected-as-intended'
        with patch.object(gate, 'controls_state', faulty):
            self.assertTrue(any(round_trip(state) != state for state in VALID[:2000]),
                            'a mapping that ignores negative controls must break the round trip')


if __name__ == '__main__':
    unittest.main()
