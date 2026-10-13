"""Generate shape agreement checks using an independent axis-constraint oracle."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from hypothesis import example, given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.semantics import SemanticFailure, agreement

EXTENT = st.one_of(st.sampled_from((0, 1)), st.integers(min_value=0, max_value=10**6))
SHAPE = st.lists(EXTENT, max_size=6)
GENERATED = settings(max_examples=250, derandomize=True, deadline=None)


def shape_oracle(left, right, broadcasting):
    """Solve aligned axis constraints; zero with unit yields zero, zero with two fails."""
    if not broadcasting and left and right and left != right:
        return None
    dimensions = []
    for axis in range(1, max(len(left), len(right)) + 1):
        extents = {shape[-axis] for shape in (left, right) if axis <= len(shape)}
        constraints = extents - {1}
        if len(constraints) > 1:
            return None
        dimensions.append(next(iter(constraints), 1))
    return dimensions[::-1]


@st.composite
def compatible_shapes(draw):
    """Build matching or unit axis constraints with independently varied ranks."""
    target = draw(SHAPE)
    operands = []
    for _operand in range(2):
        rank = draw(st.integers(min_value=0, max_value=len(target)))
        suffix = target[len(target) - rank:] if rank else []
        operands.append([draw(st.sampled_from((1, extent))) for extent in suffix])
    return tuple(operands)


@st.composite
def incompatible_shapes(draw):
    """Generate a guaranteed trailing non-unit disagreement, such as zero versus two."""
    first = draw(st.one_of(st.just(0), st.integers(min_value=2, max_value=10**6)))
    second = 2 if first == 0 else 0
    return draw(SHAPE) + [first], draw(SHAPE) + [second]


class GeneratedShapeAgreement(unittest.TestCase):
    """Distinguish broadcast constraints from equality-only array agreement."""

    def assert_agreement_matches_oracle(self, left, right, broadcasting):
        """Compare both operand orders; incompatible constraints must raise ShapeAgreement."""
        expected = shape_oracle(left, right, broadcasting)
        self.assertEqual(expected, shape_oracle(right, left, broadcasting))
        for first, second in ((left, right), (right, left)):
            if expected is None:
                with self.assertRaises(SemanticFailure) as failure:
                    agreement(first, second, broadcasting)
                self.assertEqual(str(failure.exception), 'ShapeAgreement')
            else:
                self.assertEqual(agreement(first, second, broadcasting), expected)
                self.assertEqual(len(expected), max(len(first), len(second)))

    @GENERATED
    @given(left=SHAPE, right=SHAPE)
    @example(left=[], right=[0, 1, 2])
    @example(left=[0, 1], right=[1, 3])
    @example(left=[0], right=[2])
    @example(left=[2, 1, 4], right=[3, 4])
    def test_arbitrary_broadcast_shapes_match_constraints_and_symmetry(self, left, right):
        self.assert_agreement_matches_oracle(left, right, True)

    @GENERATED
    @given(shapes=compatible_shapes())
    @example(shapes=([0, 1], [1, 3]))
    @example(shapes=([], []))
    def test_compatible_broadcast_pairs_produce_right_aligned_results(self, shapes):
        left, right = shapes
        self.assertIsNotNone(shape_oracle(left, right, True))
        self.assert_agreement_matches_oracle(left, right, True)

    @GENERATED
    @given(shapes=incompatible_shapes())
    @example(shapes=([0], [2]))
    @example(shapes=([2, 3], [4, 2]))
    def test_incompatible_broadcast_pairs_raise_shape_agreement(self, shapes):
        left, right = shapes
        self.assertIsNone(shape_oracle(left, right, True))
        self.assert_agreement_matches_oracle(left, right, True)

    @GENERATED
    @given(left=SHAPE, right=SHAPE)
    @example(left=[], right=[0, 2])
    @example(left=[0, 2], right=[0, 2])
    @example(left=[1], right=[0])
    @example(left=[2], right=[1, 2])
    def test_disabled_broadcast_requires_equal_arrays_but_accepts_scalars(self, left, right):
        self.assert_agreement_matches_oracle(left, right, False)

    def test_zero_unit_and_scalar_boundaries_remain_distinct(self):
        self.assertEqual(agreement([0], [1], True), [0])
        self.assertEqual(agreement([0, 1], [1, 3], True), [0, 3])
        for broadcasting in (False, True):
            self.assertEqual(agreement([], [], broadcasting), [])
            self.assertEqual(agreement([], [0, 2], broadcasting), [0, 2])
            self.assertEqual(agreement([0, 2], [0, 2], broadcasting), [0, 2])
        for left, right, broadcasting in (([0], [2], True), ([1], [0], False),
                                           ([2], [1, 2], False)):
            with self.subTest(left=left, right=right, broadcasting=broadcasting):
                with self.assertRaisesRegex(SemanticFailure, '^ShapeAgreement$'):
                    agreement(left, right, broadcasting)


if __name__ == '__main__':
    unittest.main()
