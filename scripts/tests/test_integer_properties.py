"""Generate I64 model checks against an independent unbounded-integer oracle."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.semantics import (
    SemanticFailure, checked_add, checked_subtract, evaluate, left_reduce, right_reduce,
)

I64_MIN = -(2**63)
I64_MAX = 2**63 - 1
I64 = st.one_of(st.sampled_from((I64_MIN, I64_MAX, -1, 0, 1)),
                st.integers(min_value=I64_MIN, max_value=I64_MAX))
GENERATED = settings(max_examples=200, derandomize=True, deadline=None)


def integer_oracle(left, right, operation):
    """Use unbounded arithmetic; max-I64 plus one records IntegerOverflow."""
    value = left + right if operation == 'add' else left - right
    return ('value', value) if I64_MIN <= value <= I64_MAX else ('error', 'IntegerOverflow')


def sequence_oracle(values, operation, association):
    """Record ordered intermediate steps; right subtraction on [10, 3, 2] yields 9."""
    rightward = association == 'right'
    accumulator = values[-1] if rightward else values[0]
    remaining = reversed(values[:-1]) if rightward else values[1:]
    trace = []
    for value in remaining:
        left, right = (value, accumulator) if rightward else (accumulator, value)
        outcome = integer_oracle(left, right, operation)
        trace.append((left, right, outcome))
        if outcome[0] == 'error':
            return outcome, trace
        accumulator = outcome[1]
    return ('value', accumulator), trace


def model_outcome(call):
    """Capture model values or named failures; an overflowing call returns its error."""
    try:
        return ('value', call())
    except SemanticFailure as error:
        return ('error', str(error))


class GeneratedIntegerModels(unittest.TestCase):
    """Check operation pairs, each reduction step, scan prefixes, and null policy."""

    @GENERATED
    @given(left=I64, right=I64, operation=st.sampled_from(('add', 'sub')))
    def test_checked_binary_matches_unbounded_integer_oracle(self, left, right, operation):
        model = checked_add if operation == 'add' else checked_subtract
        self.assertEqual(model_outcome(lambda: model(left, right)),
                         integer_oracle(left, right, operation))

    @GENERATED
    @given(values=st.lists(I64, min_size=1, max_size=8),
           operation=st.sampled_from(('add', 'sub')),
           association=st.sampled_from(('left', 'right')))
    def test_reductions_match_each_ordered_intermediate_operation(self, values, operation, association):
        expected, expected_trace = sequence_oracle(values, operation, association)
        reducer = left_reduce if association == 'left' else right_reduce
        model = checked_add if operation == 'add' else checked_subtract
        actual_trace = []

        def traced_operation(left, right):
            outcome = model_outcome(lambda: model(left, right))
            actual_trace.append((left, right, outcome))
            if outcome[0] == 'error':
                raise SemanticFailure(outcome[1])
            return outcome[1]

        self.assertEqual(model_outcome(lambda: reducer(values, traced_operation)), expected)
        self.assertEqual(actual_trace, expected_trace)
        if operation == 'sub':
            kind = 'fold_left' if association == 'left' else 'reduce'
            self.assertEqual(model_outcome(lambda: evaluate(
                {'kind': kind, 'input': values, 'operation': 'sub'})), expected)

    @GENERATED
    @given(values=st.lists(I64, max_size=8), association=st.sampled_from(('left', 'right')))
    def test_scans_match_ordered_prefix_oracles(self, values, association):
        expected_values = []
        expected = ('value', expected_values)
        for length in range(1, len(values) + 1):
            outcome, _trace = sequence_oracle(values[:length], 'sub', association)
            if outcome[0] == 'error':
                expected = outcome
                break
            expected_values.append(outcome[1])
        kind = 'scan_left' if association == 'left' else 'scan'
        self.assertEqual(model_outcome(lambda: evaluate(
            {'kind': kind, 'input': values, 'operation': 'sub'})), expected)

    @GENERATED
    @given(values=st.lists(st.one_of(I64, st.none()), max_size=8), skip_nulls=st.booleans())
    def test_nullable_sum_matches_right_associated_integer_oracle(self, values, skip_nulls):
        valid = [value for value in values if value is not None]
        if not skip_nulls and None in values:
            expected = ('value', None)
        elif not valid:
            expected = ('value', 0)
        else:
            expected, _trace = sequence_oracle(valid, 'add', 'right')
        self.assertEqual(model_outcome(lambda: evaluate(
            {'kind': 'sum', 'input': values, 'skip_nulls': skip_nulls})), expected)


if __name__ == '__main__':
    unittest.main()
