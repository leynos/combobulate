"""Property tests for the decision supersession graph invariant."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hypothesis import assume, given, settings, strategies as st

from docs_validation.decisions import check_supersession


def acyclic_supersession_graphs():
    """Generate ordered forests of valid supersession links for property checks."""
    @st.composite
    def graphs(draw):
        size = draw(st.integers(min_value=1, max_value=10))
        topology = draw(st.sampled_from(('chain', 'merge', 'forest')))
        if topology == 'chain':
            newer_for = [index + 1 if index + 1 < size else None for index in range(size)]
        elif topology == 'merge':
            newer_for = [size - 1 if index + 1 < size else None for index in range(size)]
        else:
            newer_for = [
                draw(st.one_of(st.none(), st.integers(min_value=index + 1, max_value=size - 1)))
                if index < size - 1 else None
                for index in range(size)
            ]
        supersedes = {index: [] for index in range(size)}
        for older, newer in enumerate(newer_for):
            if newer is not None:
                supersedes[newer].append(older)
        order = draw(st.permutations(tuple(range(size))))
        return {
            f'D{index:02}': {
                'id': f'D{index:02}',
                'supersedes': [f'D{older:02}' for older in supersedes[index]],
                'superseded_by': None if newer_for[index] is None else f'D{newer_for[index]:02}',
                'lifecycle': ('superseded' if newer_for[index] is not None else
                              'accepted' if supersedes[index] else 'proposed'),
            }
            for index in order
        }

    return graphs()


def supersession_cycles():
    """Generate reciprocal cycles of three or more decisions in varied record order."""
    @st.composite
    def cycles(draw):
        size = draw(st.integers(min_value=3, max_value=8))
        order = draw(st.permutations(tuple(range(size))))
        return {
            f'D{index:02}': {
                'id': f'D{index:02}',
                'supersedes': [f'D{(index - 1) % size:02}'],
                'superseded_by': f'D{(index + 1) % size:02}',
                'lifecycle': 'superseded',
            }
            for index in order
        }

    return cycles()


class SupersessionProperties(unittest.TestCase):
    """Exercise acyclic graphs, cycles, and record ordering over generated cases."""

    @settings(max_examples=100, derandomize=True, deadline=None)
    @given(records=acyclic_supersession_graphs())
    def test_acyclic_chains_and_merges_pass_in_any_record_order(self, records):
        check_supersession(records)

    @settings(max_examples=50, derandomize=True, deadline=None)
    @given(records=supersession_cycles())
    def test_reciprocal_cycles_fail_regardless_of_record_order(self, records):
        with self.assertRaisesRegex(AssertionError, 'Supersession cycle'):
            check_supersession(records)

    @settings(max_examples=100, derandomize=True, deadline=None)
    @given(records=acyclic_supersession_graphs())
    def test_one_way_links_fail_for_generated_acyclic_graphs(self, records):
        edges = [(record['id'], older) for record in records.values() for older in record['supersedes']]
        assume(bool(edges))
        newer, older = edges[0]
        records[newer]['supersedes'].remove(older)
        with self.assertRaisesRegex(AssertionError, 'One-way supersession'):
            check_supersession(records)

    @settings(max_examples=100, derandomize=True, deadline=None)
    @given(records=acyclic_supersession_graphs())
    def test_unknown_links_fail_for_generated_acyclic_graphs(self, records):
        next(iter(records.values()))['supersedes'].append('D99')
        with self.assertRaisesRegex(AssertionError, 'supersedes unknown D99'):
            check_supersession(records)

    @settings(max_examples=100, derandomize=True, deadline=None)
    @given(records=acyclic_supersession_graphs())
    def test_proposed_replacements_fail_for_generated_acyclic_graphs(self, records):
        edges = [(record['id'], older) for record in records.values() for older in record['supersedes']]
        assume(bool(edges))
        replacement, _older = edges[0]
        records[replacement]['lifecycle'] = 'proposed'
        with self.assertRaisesRegex(AssertionError, 'must be accepted before superseding'):
            check_supersession(records)


if __name__ == '__main__':
    unittest.main()
