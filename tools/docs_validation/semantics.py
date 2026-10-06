"""Validate semantics claims in the design pack without claiming Rust evidence."""
from __future__ import annotations

import math
import operator
from .context import ValidationContext, require
from .semantic_domains import (
    validate_board, validate_boolean, validate_i64, validate_i64_values, validate_integer_values,
    validate_shape, validate_subtraction,
)


class SemanticFailure(Exception):
    """Named failure in this small documentation-example model."""


def checked_add(left: int, right: int) -> int:
    """Add signed i64 values; checked_add(2**63 - 1, 1) raises overflow."""
    validate_i64(left)
    validate_i64(right)
    result = left+right
    if not -(2**63) <= result < 2**63:
        raise SemanticFailure('IntegerOverflow')
    return result


def right_reduce(values: list[int], operation) -> int:
    """Associate from the right; subtraction on [10, 3, 2] yields 9."""
    if not values:
        raise SemanticFailure('EmptyReduction')
    result=values[-1]
    for value in reversed(values[:-1]):
        result=operation(value,result)
    return result


def left_reduce(values: list[int], operation) -> int:
    """Associate from the left; subtraction on [10, 3, 2] yields 5."""
    if not values:
        raise SemanticFailure('EmptyReduction')
    result=values[0]
    for value in values[1:]:
        result=operation(result,value)
    return result


def agreement(left: list[int], right: list[int], broadcasting: bool) -> list[int]:
    """Agree scalar/array shapes; agreement([], [3], False) yields [3]."""
    validate_shape(left)
    validate_shape(right)
    validate_boolean(broadcasting, 'broadcast policy')
    if left==right or not right:
        return left
    if not left:
        return right
    if not broadcasting:
        raise SemanticFailure('ShapeAgreement')
    width=max(len(left),len(right))
    a=[1]*(width-len(left))+left
    b=[1]*(width-len(right))+right
    out=[]
    for x,y in zip(a,b):
        if x==y:
            out.append(x)
        elif x==1:
            out.append(y)
        elif y==1:
            out.append(x)
        else:
            raise SemanticFailure('ShapeAgreement')
    return out


def subtract_reduce(case: dict):
    """Model association explicitly; [10, 3, 2] gives 9 rightwards and 5 leftwards."""
    validate_subtraction(case)
    reducer = right_reduce if case['kind'] == 'reduce' else left_reduce
    return reducer(case['input'], operator.sub)


def subtract_scan(case: dict) -> list[int]:
    """Reduce every prefix; right subtraction over [10, 3, 2] gives [10, 7, 9]."""
    validate_subtraction(case)
    reducer = right_reduce if case['kind'] == 'scan' else left_reduce
    return [reducer(case['input'][:i], operator.sub)
            for i in range(1, len(case['input']) + 1)]


def rank_transpose_shape(case: dict) -> list[int]:
    """Reverse cell axes only; rank two maps [4, 2, 3] to [4, 3, 2]."""
    rank, shape = case['cell_rank'], case['input_shape']
    validate_shape(shape)
    require(type(rank) is int and 0 <= rank <= len(shape), 'Malformed cell rank')
    return shape[:-rank] + shape[-rank:][::-1] if rank else shape


def rows_mean_shape(case: dict) -> list[int]:
    """Drop the final axis; [2, 0] fails but [0, 0] has no empty cells to average."""
    shape = case['input_shape']
    validate_shape(shape)
    require(bool(shape), 'Malformed row-mean shape: expected at least one axis')
    if shape[-1] == 0 and math.prod(shape[:-1]) > 0:
        raise SemanticFailure('EmptyMean')
    return shape[:-1]


def shape_agreement(case: dict) -> list[int]:
    """Apply the explicit broadcast policy; e.g. [2, 1] and [3] yield [2, 3]."""
    return agreement(case['left'], case['right'], case['broadcast'])


def nullable_sum(case: dict) -> int | None:
    """Sum valid values; [1, None] yields 1 when skipping nulls, otherwise None."""
    values = case['input']
    validate_boolean(case['skip_nulls'], 'null policy')
    validate_integer_values(values, nullable=True)
    if not case['skip_nulls'] and None in values:
        return None
    return sum(value for value in values if value is not None)


def neighbours(board: list[list[int]], y: int, x: int):
    """Yield in-bounds neighbouring values; corner (0, 0) excludes row wrapping."""
    for yy in range(max(0, y - 1), min(len(board), y + 2)):
        for xx in range(max(0, x - 1), min(len(board[0]), x + 2)):
            if (yy, xx) != (y, x):
                yield board[yy][xx]


def neighbour_sum(case: dict) -> list[list[int]]:
    """Model a bounded 2-D stencil; [[1, 0]] maps to [[0, 1]]."""
    board = case['input']
    validate_board(board)
    return [[sum(neighbours(board, y, x)) for x in range(len(board[0]))]
            for y in range(len(board))]


def inner_shape(case: dict) -> list[int]:
    """Contract matching axes; [2, 3] with [3, 4] yields [2, 4]."""
    left, right = case['left'], case['right']
    validate_shape(left)
    validate_shape(right)
    require(bool(left) and bool(right), 'Malformed contraction shape: expected at least one axis')
    if left[-1] != right[0]:
        raise SemanticFailure('Contraction')
    return left[:-1] + right[1:]


def reshape(case: dict) -> list[int]:
    """Require equal element counts; [2, 3] can reshape to [6], but not [5]."""
    validate_shape(case['input_shape'])
    validate_shape(case['target_shape'])
    if math.prod(case['input_shape']) != math.prod(case['target_shape']):
        raise SemanticFailure('ElementCount')
    return case['target_shape']


def checked_add_grouping(case: dict) -> int:
    """Use checked i64 arithmetic with the specified association; overflow fails."""
    association = case['association']
    validate_i64_values(case['input'])
    require(association in {'left', 'right'}, f'Unknown checked-add association {association}')
    reducer = right_reduce if association == 'right' else left_reduce
    return reducer(case['input'], checked_add)


EXAMPLE_MODELS = {
    'reduce': subtract_reduce, 'fold_left': subtract_reduce,
    'scan': subtract_scan, 'scan_left': subtract_scan,
    'rank_transpose_shape': rank_transpose_shape, 'rows_mean_shape': rows_mean_shape,
    'agreement': shape_agreement, 'sum': nullable_sum, 'neighbour_sum': neighbour_sum,
    'inner_shape': inner_shape, 'reshape': reshape,
    'checked_add_grouping': checked_add_grouping,
}


def evaluate(case: dict):
    """Dispatch a documentation model; unknown example kinds fail explicitly."""
    kind = case['kind']
    require(kind in EXAMPLE_MODELS, f'Unrecognized example kind: {kind}')
    return EXAMPLE_MODELS[kind](case)


def check_examples(context: ValidationContext) -> None:
    """Check examples and wrong-algorithm controls, without invoking Rust kernels."""
    cases=context.load('spec/examples.json')['cases']
    for case in cases:
        try:
            result=evaluate(case)
        except SemanticFailure as error:
            require(str(error)==case.get('expected_error'), f'Wrong failure in {case["id"]}: {error}')
        else:
            require('expected_error' not in case, f'Missing error in {case["id"]}')
            expected=case['expected_shape'] if 'expected_shape' in case else case.get('expected')
            require(result==expected, f'Wrong result in {case["id"]}: {result}, expected {expected}')
    require(right_reduce([10,3,2],lambda a,b:a-b)!=left_reduce([10,3,2],lambda a,b:a-b),
            'Association control is vacuous')
    board=[[1,0,0],[0,0,1]]
    correct=evaluate(dict(kind='neighbour_sum',input=board))
    flat=sum(board,[])
    # A deliberately faulty stencil checks flattened bounds but not columns.
    bad=[sum(flat[j] for offset in [-4,-3,-2,-1,1,2,3,4]
             if 0 <= (j:=i+offset) < len(flat)) for i in range(len(flat))]
    require(sum(correct,[])!=bad,'Flattened-row-leakage negative control is vacuous')
    require(len({c['id'] for c in cases})==len(cases),'Duplicate example IDs')
    context.record('semantic-examples', 'Small Python specification model checks expected values/shapes/errors; association and flattened-row-leakage controls distinguish wrong algorithms. Zero-kernel-call claims remain future Rust obligations, not measured here.', len(cases))
