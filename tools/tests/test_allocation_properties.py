"""Generate allocation accounting checks using a capacity-membership oracle.

Run this module directly with::

    python tools/tests/test_allocation_properties.py
"""
from __future__ import annotations

import copy
import string
import sys
import unittest
from pathlib import Path
from typing import TypedDict, cast

from hypothesis import example, given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.costs import tracked_peak, tracked_stage_bytes

ALLOCATION_ID = st.text(alphabet=string.ascii_letters + string.digits + '_-', max_size=10)
BYTES = st.one_of(st.just(0), st.integers(min_value=0, max_value=2**80))
CAPACITIES = st.dictionaries(ALLOCATION_ID, BYTES, max_size=8)
GENERATED = settings(max_examples=250, derandomize=True, deadline=None)


class Stage(TypedDict):
    """Describe one generated stage's allocation references and scratch bytes."""

    live: list[str]
    scratch: int


class Case(TypedDict):
    """Describe the test-local allocation capacities and ordered stages."""

    capacities: dict[str, int]
    stages: list[Stage]


@st.composite
def allocation_cases(draw: st.DrawFn) -> Case:
    """Create valid alias-bearing or scratch-only stages with nonnegative capacities."""
    capacities = draw(CAPACITIES)
    ids = tuple(capacities)
    live = st.lists(st.sampled_from(ids), max_size=15) if ids else st.just([])
    stage = cast(st.SearchStrategy[Stage], st.fixed_dictionaries({'live': live, 'scratch': BYTES}))
    return {'capacities': capacities, 'stages': draw(st.lists(stage, min_size=1, max_size=7))}


def stage_oracle(stage: Stage, capacities: dict[str, int]) -> int:
    """Count each capacity by membership; two references to allocation 'a' charge it once."""
    total = stage['scratch']
    for allocation_id, capacity in capacities.items():
        if allocation_id in stage['live']:
            total += capacity
    return total


def peak_oracle(case: Case) -> int:
    """Track the largest membership-accounted stage, including scratch-only stages."""
    peak = 0
    for stage in case['stages']:
        total = stage_oracle(stage, case['capacities'])
        if total > peak:
            peak = total
    return peak


class GeneratedAllocationAccounting(unittest.TestCase):
    """Check independent accounting, alias/order invariance, and monotonic peak changes."""

    @GENERATED
    @given(case=allocation_cases())
    @example(case={'capacities': {}, 'stages': [{'live': [], 'scratch': 0}]})
    @example(case={'capacities': {'a': 0}, 'stages': [{'live': ['a', 'a'], 'scratch': 7}]})
    @example(case={'capacities': {'a': 80, 'b': 40}, 'stages': [
        {'live': ['a', 'a'], 'scratch': 8}, {'live': ['a', 'b'], 'scratch': 16}]})
    def test_stage_and_peak_totals_match_capacity_membership_oracle(self, case: Case) -> None:
        for stage in case['stages']:
            self.assertEqual(tracked_stage_bytes(stage, case['capacities']),
                             stage_oracle(stage, case['capacities']))
        self.assertEqual(tracked_peak(case), peak_oracle(case))

    @GENERATED
    @given(case=allocation_cases())
    @example(case={'capacities': {'a': 80}, 'stages': [{'live': ['a'], 'scratch': 8}]})
    def test_repeating_live_allocation_ids_preserves_stage_and_peak_totals(self, case: Case) -> None:
        repeated = copy.deepcopy(case)
        for original, stage in zip(case['stages'], repeated['stages']):
            stage['live'] *= 2
            self.assertEqual(tracked_stage_bytes(stage, case['capacities']),
                             stage_oracle(original, case['capacities']))
        self.assertEqual(tracked_peak(repeated), peak_oracle(case))

    @GENERATED
    @given(case=allocation_cases(), data=st.data())
    def test_reordering_live_ids_and_stages_preserves_accounting(
        self, case: Case, data: st.DataObject,
    ) -> None:
        reordered = copy.deepcopy(case)
        for stage in reordered['stages']:
            expected = stage_oracle(stage, case['capacities'])
            stage['live'] = list(data.draw(st.permutations(stage['live'])))
            self.assertEqual(tracked_stage_bytes(stage, case['capacities']), expected)
        reordered['stages'] = list(data.draw(st.permutations(reordered['stages'])))
        self.assertEqual(tracked_peak(reordered), peak_oracle(case))

    @GENERATED
    @given(case=allocation_cases(), increase=BYTES, data=st.data())
    def test_increasing_stage_scratch_cannot_reduce_peak(
        self, case: Case, increase: int, data: st.DataObject,
    ) -> None:
        expanded = copy.deepcopy(case)
        index = data.draw(st.integers(min_value=0, max_value=len(case['stages']) - 1))
        stage = expanded['stages'][index]
        expected_stage = stage_oracle(stage, case['capacities']) + increase
        stage['scratch'] += increase
        self.assertEqual(tracked_stage_bytes(stage, expanded['capacities']), expected_stage)
        self.assertEqual(tracked_peak(expanded), peak_oracle(expanded))
        self.assertGreaterEqual(tracked_peak(expanded), peak_oracle(case))

    @GENERATED
    @given(case=allocation_cases(), capacity=BYTES, identifier=ALLOCATION_ID, data=st.data())
    def test_adding_distinct_live_allocation_cannot_reduce_peak(
        self, case: Case, capacity: int, identifier: str, data: st.DataObject,
    ) -> None:
        expanded = copy.deepcopy(case)
        allocation_id = 'new:' + identifier
        self.assertNotIn(allocation_id, expanded['capacities'])
        index = data.draw(st.integers(min_value=0, max_value=len(case['stages']) - 1))
        stage = expanded['stages'][index]
        expected_stage = stage_oracle(stage, case['capacities']) + capacity
        expanded['capacities'][allocation_id] = capacity
        stage['live'].append(allocation_id)
        self.assertEqual(tracked_stage_bytes(stage, expanded['capacities']), expected_stage)
        self.assertEqual(tracked_peak(expanded), peak_oracle(expanded))
        self.assertGreaterEqual(tracked_peak(expanded), peak_oracle(case))


if __name__ == '__main__':
    unittest.main()
