"""Prove the semantic contract records are complete and non-vacuous (VO-8, VO-10)."""
from __future__ import annotations

import copy
import math
import struct
import sys
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hypothesis import given, settings, strategies as st
from jsonschema import Draft202012Validator, ValidationError

from check_docs import collect_checks
from docs_validation.context import ValidationContext, same_typed_value
from docs_validation.contract_examples import check_contract_examples, decode, encode, evaluate_contract, outcome
from docs_validation.semantic_contracts import check_macro_grammar, check_semantic_contracts
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

    def test_composed_checker_records_semantic_contract_checks_once(self):
        """Keep each contract checker connected to the complete validation path."""
        context = ValidationContext(ROOT)
        collect_checks(context)
        checks = [result['check'] for result in context.results]
        for check in ('contract-examples', 'semantic-contracts', 'macro-grammar'):
            with self.subTest(check=check):
                self.assertEqual(checks.count(check), 1,
                                 f'the composed checker must record {check} exactly once')

    def test_schema_requires_all_register_fields(self):
        """Reject a contract register missing a schema-required field."""
        register = copy.deepcopy(CONTRACTS)
        register.pop('revision')
        with self.assertRaises(ValidationError):
            run_with({'spec/semantic-contracts.json': register})

    def test_schema_rejects_undeclared_register_fields(self):
        """Reject undeclared contract-register data at the checker boundary."""
        register = copy.deepcopy(CONTRACTS) | {'unexpected': True}
        with self.assertRaises(ValidationError):
            run_with({'spec/semantic-contracts.json': register})

    def test_schema_accepts_example_identifiers_above_two_digits(self):
        """Keep future example identifiers valid after the current two-digit range."""
        register = copy.deepcopy(CONTRACTS)
        record(register, 'SC-01')['examples'].append('EX100')
        validator = Draft202012Validator(CONTEXT.load('spec/semantic-contract.schema.json'))
        validator.validate(register)

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

    def test_sc04_requires_every_numeric_arithmetic_entry(self):
        """Require SC-04 links for addition, subtraction, multiplication, and casts."""
        for missing_id in ('V002', 'V003'):
            with self.subTest(catalogue_id=missing_id):
                register = contracts_with(lambda r: record(r, 'SC-04')['catalogue_ids'].remove(missing_id))
                self.assert_rejected('spec/semantic-contracts.json', register,
                                     'SC-04 must cite add, sub, mul, and cast catalogue entries')

    def test_sc01_requires_empty_reduction_error_relation(self):
        """Keep empty reduction failures in the structured SC-01 relations."""
        register = contracts_with(lambda r: record(r, 'SC-01')['error_relation'].remove(
            next(relation for relation in record(r, 'SC-01')['error_relation']
                 if relation['error'] == 'EmptyReduction')))
        self.assert_rejected('spec/semantic-contracts.json', register,
                             'SC-01 must register EmptyReduction for empty reduce and fold_left lanes')

    def test_sc08_requires_negative_axis_error_relation(self):
        """Keep negative-axis rejection visible in the SC-08 error relation."""
        register = contracts_with(lambda r: next(
            relation for relation in record(r, 'SC-08')['error_relation']
            if relation['error'] == 'AxisOutOfRange').update(
                condition='An axis is at or beyond the frame rank.'))
        self.assert_rejected('spec/semantic-contracts.json', register,
                             'SC-08 must register rejection of negative axes')

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
        for name, normalized in (('cells', 'cells'), ('.pipe(f)', '.pipe')):
            with self.subTest(name=name):
                vocabulary = CONTEXT.load('spec/vocabulary.json')
                vocabulary['entries'].append(copy.deepcopy(vocabulary['entries'][0]) |
                                              {'id': 'V999', 'name': f'`{name}`'})
                self.assert_rejected('spec/vocabulary.json', vocabulary,
                                     f'Excluded name {normalized} appears in the catalogue')

    def test_macro_grammar_covers_all_five_public_forms(self):
        check_macro_grammar(ValidationContext(ROOT))

    def test_macro_grammar_requires_pipeline_argument_coverage(self):
        """Require a corpus witness for pipelines inside ordinary call arguments."""
        grammar = copy.deepcopy(CONTEXT.load('spec/macro-grammar.json'))
        grammar['corpus'] = [entry for entry in grammar['corpus'] if entry['id'] != 'G29']
        context = ValidationContext(ROOT)
        original = context.load
        with self.assertRaisesRegex(AssertionError, 'Grammar corpus misses pipeline-argument'):
            with patch.object(context, 'load', lambda name: copy.deepcopy(grammar)
                              if name == 'spec/macro-grammar.json' else original(name)):
                check_macro_grammar(context)

    def test_macro_grammar_rejects_a_missing_public_form_production(self):
        source = (ROOT / 'docs/adrs/adr-0007-comb-macro-grammar-and-staging.md').read_text(encoding='utf-8')
        source = source.replace(
            'host-block    = "host" , "{" , rust-token-tree , "}" ;        (* host Rust, evaluated once *)\n', '', 1)
        with TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            adr_path = temporary_root / 'docs/adrs/adr-0007-comb-macro-grammar-and-staging.md'
            adr_path.parent.mkdir(parents=True)
            adr_path.write_text(source, encoding='utf-8')
            context = ValidationContext(temporary_root)
            with patch.object(context, 'load', lambda name: CONTEXT.load(name)):
                with self.assertRaisesRegex(AssertionError, 'ADR-0007 grammar misses productions: host-block'):
                    check_macro_grammar(context)


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

    @GENERATED
    @given(values=st.lists(
        st.one_of(
            st.integers(min_value=-1000, max_value=1000),
            st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
            st.none(),
        ), max_size=8),
        skip_nulls=st.booleans(),
        operation=st.sampled_from(('variance', 'stddev')),
        ddof=st.integers(min_value=0, max_value=8))
    def test_variance_matches_independent_sequential_two_pass_oracle(self, values, skip_nulls, operation, ddof):
        """Compare generated variance cases with a separate sequential two-pass calculation."""
        case = {'operation': operation, 'input': values, 'skip_nulls': skip_nulls, 'ddof': ddof}
        if not skip_nulls and any(value is None for value in values):
            expected = None
        else:
            valid_values = [float(value) for value in values if value is not None]
            if len(valid_values) <= ddof:
                expected = {'error': 'InsufficientCount'}
            else:
                reversed_values = iter(reversed(valid_values))
                mean_total = next(reversed_values)
                for value in reversed_values:
                    mean_total = value + mean_total
                mean = mean_total / float(len(valid_values))

                reversed_deviations = iter(reversed(valid_values))
                deviation = next(reversed_deviations) - mean
                squared_total = deviation * deviation
                for value in reversed_deviations:
                    deviation = value - mean
                    squared_total = deviation * deviation + squared_total
                expected_value = squared_total / float(len(valid_values) - ddof)
                if operation == 'stddev':
                    expected_value = math.sqrt(expected_value)
                expected = encode(expected_value)
        self.assertEqual(outcome(case), expected,
                         'variance and stddev must match sequential two-pass arithmetic and null rules')

    @GENERATED
    @given(destination=st.lists(I64, max_size=8), output=st.lists(I64, max_size=8), data=st.data())
    def test_atomic_commit_preserves_destination_until_complete_success(self, destination, output, data):
        """Exercise success and failure across generated destination and output lengths."""
        fail_at = data.draw(st.one_of(st.none(), st.integers(min_value=0, max_value=len(output))))
        case = {'operation': 'atomic_commit', 'destination': destination, 'output': output, 'fail_at': fail_at}
        expected = output if fail_at is None else destination
        self.assertEqual(evaluate_contract(case), expected,
                         'failure before output commit preserves the complete original destination')

    def test_every_contract_example_matches_its_expectation(self):
        for case in CONTEXT.load('spec/examples.json')['contract_cases']:
            with self.subTest(case=case['id']):
                expected = {'error': case['expected_error']} if 'expected_error' in case else encode(
                    decode(case['expected']))
                self.assertTrue(same_typed_value(outcome(case), expected),
                                'the documentation model must reproduce the typed example')

    def test_large_finite_deviations_overflow_to_ieee_infinity(self):
        cases = {case['id']: case for case in CONTEXT.load('spec/examples.json')['contract_cases']}
        for example_id in ('EX82', 'EX83'):
            with self.subTest(example=example_id):
                self.assertEqual(outcome(cases[example_id]), {'f64': 'inf'},
                                 'finite F64 deviations whose squares overflow produce positive infinity')

    def test_empty_reduce_and_fold_left_without_identity_fail(self):
        """Keep both empty reduction forms aligned with the registered error."""
        cases = {case['id']: case for case in CONTEXT.load('spec/examples.json')['contract_cases']}
        for example_id in ('EX84', 'EX85'):
            with self.subTest(example=example_id):
                self.assertEqual(outcome(cases[example_id]), {'error': 'EmptyReduction'},
                                 'empty reduce and fold_left without identity must fail')

    def test_negative_batch_axis_fails(self):
        """Reject a negative frame axis instead of treating it as a valid index."""
        cases = {case['id']: case for case in CONTEXT.load('spec/examples.json')['contract_cases']}
        self.assertEqual(outcome(cases['EX86']), {'error': 'AxisOutOfRange'},
                         'frame axes are zero-based and negative indices are rejected')

    def test_each_numeric_binary_primitive_rejects_mixed_dtypes(self):
        """Prevent mixed-dtype promotion for each numeric binary primitive."""
        cases = {case['id']: case for case in CONTEXT.load('spec/examples.json')['contract_cases']}
        for example_id in ('EX47', 'EX87', 'EX88'):
            with self.subTest(example=example_id):
                self.assertEqual(outcome(cases[example_id]), {'error': 'DtypeMismatch'},
                                 'add, sub, and mul must reject implicit dtype promotion')

    def test_contract_example_rejects_bool_integer_expectation_coercion(self):
        examples = copy.deepcopy(CONTEXT.load('spec/examples.json'))
        next(case for case in examples['contract_cases'] if case['id'] == 'EX26')['expected'] = 0
        context = ValidationContext(ROOT)
        original = context.load
        with patch.object(context, 'load', lambda name: examples if name == 'spec/examples.json' else original(name)):
            with self.assertRaisesRegex(AssertionError, 'EX26 expected 0, got False'):
                check_contract_examples(context)


if __name__ == '__main__':
    unittest.main()
