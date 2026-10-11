"""Prove the semantic contract records are complete and non-vacuous (VO-8, VO-10)."""
from __future__ import annotations

import copy
import math
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hypothesis import given, settings, strategies as st

from docs_validation.context import ValidationContext
from docs_validation.contract_examples import decode, encode, evaluate_contract, outcome
from docs_validation.semantic_contracts import check_semantic_contracts
from docs_validation.semantics import SemanticFailure

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = ValidationContext(ROOT)
CONTRACTS = CONTEXT.load('spec/semantic-contracts.json')
GENERATED = settings(max_examples=300, derandomize=True, deadline=None)
I64 = st.integers(-(2**63), 2**63 - 1)
REQUIRED_MUTATIONS = {'left-reduce', 'floor-idiv', 'empty-sum-error', 'identity-as-seed', 'implicit-promotion',
                      'nan-ignoring-min', 'two-valued-logic', 'exact-quotient-div', 'partial-output',
                      'cell-flattening', 'right-associative-pipe'}


def run_with(overrides: dict[str, object]) -> None:
    """Run the contract check with some loaded documents replaced in memory."""
    context = ValidationContext(ROOT)
    original = context.load
    with patch.object(context, 'load', lambda name: copy.deepcopy(overrides.get(name)) if name in overrides
                      else original(name)):
        check_semantic_contracts(context)


def contracts_with(edit) -> dict:
    """Return a copy of the contract register after applying an in-place edit."""
    register = copy.deepcopy(CONTRACTS)
    edit(register)
    return register


def record(register: dict, contract_id: str) -> dict:
    """Return one mutable contract record."""
    return next(entry for entry in register['contracts'] if entry['id'] == contract_id)


class ContractRegister(unittest.TestCase):
    """VO-8: every record is complete and every link resolves; each fault has its own message."""

    def assert_rejected(self, name: str, document: dict, message: str) -> None:
        with self.assertRaisesRegex(AssertionError, message):
            run_with({name: document})

    def test_committed_register_passes(self):
        check_semantic_contracts(ValidationContext(ROOT))

    def test_required_seeded_mutations_are_present(self):
        named = {mutation['id'] for entry in CONTRACTS['contracts'] for mutation in entry['seeded_mutations']}
        self.assertLessEqual(REQUIRED_MUTATIONS, named, 'every planned seeded mutation must be named by a record')

    def test_unknown_catalogue_entry_fails(self):
        register = contracts_with(lambda r: record(r, 'SC-03')['catalogue_ids'].append('V999'))
        self.assert_rejected('spec/semantic-contracts.json', register, 'SC-03 cites unknown catalogue entry V999')

    def test_catalogue_entry_must_cite_its_contract(self):
        vocabulary = CONTEXT.load('spec/vocabulary.json')
        entry = next(item for item in vocabulary['entries'] if item['id'] == 'V005')
        entry['contract'] = entry['contract'].replace(' Contract: SC-03.', '')
        self.assert_rejected('spec/vocabulary.json', vocabulary, 'Catalogue entry V005 must cite SC-03')

    def test_unregistered_error_fails(self):
        register = contracts_with(lambda r: record(r, 'SC-03')['error_relation'].append(
            {'condition': 'Anything.', 'error': 'Oops'}))
        self.assert_rejected('spec/semantic-contracts.json', register, 'SC-03 uses unregistered error Oops')

    def test_example_owned_by_another_contract_fails(self):
        register = contracts_with(lambda r: record(r, 'SC-03')['examples'].append('EX21'))
        self.assert_rejected('spec/semantic-contracts.json', register, 'EX21 belongs to SC-01, not SC-03')

    def test_uncited_example_fails(self):
        register = contracts_with(lambda r: record(r, 'SC-03')['examples'].remove('EX37'))
        self.assert_rejected('spec/semantic-contracts.json', register, 'Contract examples cited by no record: EX37')

    def test_vacuous_mutation_fails(self):
        register = contracts_with(lambda r: record(r, 'SC-03')['seeded_mutations'].append(
            {'id': 'no-op', 'description': 'Changes nothing.'}))
        self.assert_rejected('spec/semantic-contracts.json', register, 'Seeded mutation no-op changes no outcome of SC-03')

    def test_unknown_discharge_target_fails(self):
        register = contracts_with(lambda r: record(r, 'SC-03')['discharged_by'].append('PF07.proof@9.9.9'))
        self.assert_rejected('spec/semantic-contracts.json', register, 'SC-03 is discharged by unknown PF07.proof@9.9.9')

    def test_contract_needs_an_accepted_decision(self):
        decisions = CONTEXT.load('spec/decisions.json')
        entry = next(item for item in decisions['decisions'] if item['id'] == 'D14')
        entry['lifecycle'] = 'proposed'
        self.assert_rejected('spec/decisions.json', decisions, 'SC-05 cites a decision that is not accepted')

    def test_superseded_name_cannot_return_to_the_catalogue(self):
        vocabulary = CONTEXT.load('spec/vocabulary.json')
        vocabulary['entries'].append(copy.deepcopy(vocabulary['entries'][0]) | {'id': 'V999', 'name': '`cells`'})
        self.assert_rejected('spec/vocabulary.json', vocabulary, 'Excluded name cells appears in the catalogue')


class TaggedScalars(unittest.TestCase):
    """Tagged encoding keeps signed zeros, NaN payloads, and wide integers distinct."""

    def test_signed_zeros_stay_distinct(self):
        self.assertNotEqual(encode(-0.0), encode(0.0), 'negative and positive zero must not compare equal')

    def test_nan_round_trips_by_bits(self):
        tagged = {'f64_bits': '0x7ff8000000000001'}
        self.assertEqual(encode(decode(tagged)), tagged, 'a NaN payload must survive decoding and encoding')

    def test_wide_integer_round_trips(self):
        self.assertEqual(decode({'i64': '-9223372036854775808'}), -(2**63), 'I64::MIN must decode exactly')


def bits(value: float) -> int:
    """Return a float's IEEE bit pattern."""
    return struct.unpack('>Q', struct.pack('>d', value))[0]


class ContractProperties(unittest.TestCase):
    """Generated checks of the accepted rules beyond the fixed examples."""

    @GENERATED
    @given(I64, I64.filter(lambda value: value != 0))
    def test_truncating_division_identity(self, left, right):
        try:
            quotient = evaluate_contract({'operation': 'idiv', 'args': [left, right]})
        except SemanticFailure:
            self.assertEqual((left, right), (-(2**63), -1), 'only MIN / -1 may overflow')
            return
        remainder = evaluate_contract({'operation': 'rem', 'args': [left, right]})
        self.assertEqual(left, right * quotient + remainder, 'a = b*q + r')
        self.assertLess(abs(remainder), abs(right), '|r| < |b|')
        self.assertTrue(remainder == 0 or (remainder < 0) == (left < 0), 'the remainder takes the dividend sign')

    @GENERATED
    @given(st.floats(allow_nan=False), st.floats(allow_nan=False))
    def test_ieee_minimum_is_commutative_and_ordered(self, left, right):
        first = evaluate_contract({'operation': 'min', 'args': [encode(left), encode(right)]})
        second = evaluate_contract({'operation': 'min', 'args': [encode(right), encode(left)]})
        self.assertEqual(bits(first), bits(second), 'minimum is commutative bit for bit, signed zeros included')
        self.assertTrue(first <= left and first <= right, 'minimum is no greater than either operand')

    @GENERATED
    @given(st.floats(allow_nan=False))
    def test_nan_propagates_through_minimum_and_maximum(self, value):
        nan = {'f64_bits': '0x7ff8000000000000'}
        for operation in ('min', 'max'):
            result = evaluate_contract({'operation': operation, 'args': [encode(value), nan]})
            self.assertTrue(math.isnan(result), f'{operation} must propagate NaN')

    @GENERATED
    @given(I64)
    def test_i64_to_f64_round_trip_is_exact_below_two_to_the_53(self, value):
        converted = evaluate_contract({'operation': 'cast', 'input': value, 'to': 'F64'})
        if abs(value) <= 2**53:
            back = evaluate_contract({'operation': 'cast', 'input': encode(converted), 'to': 'I64'})
            self.assertEqual(back, value, 'integers within 2^53 convert exactly')

    def test_every_contract_example_matches_its_expectation(self):
        for case in CONTEXT.load('spec/examples.json')['contract_cases']:
            with self.subTest(case=case['id']):
                expected = {'error': case['expected_error']} if 'expected_error' in case else encode(
                    decode(case['expected']))
                self.assertEqual(outcome(case), expected, 'the documentation model must reproduce the example')


if __name__ == '__main__':
    unittest.main()
