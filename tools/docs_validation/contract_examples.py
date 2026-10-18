"""Evaluate the tagged-scalar examples that pin down the ADR-0006 contracts.

This is a documentation model, not the Rust implementation: it states the
accepted numeric, validity, reduction, and commit rules executably so that each
example in `spec/examples.json` (`contract_cases`) is checked, and so that each
seeded mutation named by a contract record provably changes an outcome. Values
are Python `int` (I64), `bool` (Bool), `float` (F64, IEEE binary64), and `None`
(null). JSON examples tag F64 and wide I64 values so signed zeros, NaN payloads,
and 64-bit integers survive serialization.
"""
from __future__ import annotations

import math
import struct
from collections.abc import Callable
from fractions import Fraction

from .context import ValidationContext, require, same_typed_value
from .semantics import SemanticFailure

I64_MIN, I64_MAX = -(2**63), 2**63 - 1
MEAN_COUNT_LIMIT = 2**53
Mutations = frozenset[str]


def decode(value: object) -> object:
    """Decode a tagged JSON scalar or list; e.g. {'f64': '-0.0'} becomes -0.0."""
    if isinstance(value, list):
        return [decode(item) for item in value]
    if isinstance(value, dict):
        (tag, text), = value.items()
        if tag == 'f64':
            return float(text)
        if tag == 'f64_bits':
            return struct.unpack('>d', int(text, 16).to_bytes(8, 'big'))[0]
        require(tag == 'i64', f'Unknown scalar tag {tag}')
        return int(text)
    return value


def encode(value: object) -> object:
    """Encode a model value so floats compare by bits; e.g. -0.0 becomes {'f64': '-0.0'}."""
    if isinstance(value, list):
        return [encode(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value):
            return {'f64_bits': f"0x{struct.unpack('>Q', struct.pack('>d', value))[0]:016x}"}
        return {'f64': repr(value)}
    return value


def dtype(value: object) -> str | None:
    """Name a scalar dtype; e.g. ``dtype(True)`` is ``'Bool'``."""
    if value is None:
        return None
    return {bool: 'Bool', int: 'I64', float: 'F64'}[type(value)]


def same_dtype(left: object, right: object, mutations: Mutations) -> None:
    """Reject mixed operands; e.g. I64 plus F64 raises ``DtypeMismatch``."""
    if dtype(left) != dtype(right) and 'implicit-promotion' not in mutations:
        raise SemanticFailure('DtypeMismatch')


def checked_i64(value: int) -> int:
    """Reject results outside I64; e.g. ``checked_i64(3)`` returns ``3``."""
    if not I64_MIN <= value <= I64_MAX:
        raise SemanticFailure('IntegerOverflow')
    return value


def arithmetic(operation: Callable[[object, object], object]) -> Callable[..., object]:
    """Lift arithmetic rules; e.g. an addition wrapper maps ``(2, 3)`` to ``5``."""
    def apply(left: object, right: object, mutations: Mutations) -> object:
        """Apply the lifted operation; e.g. adding ``2`` and ``3`` returns ``5``."""
        if left is None or right is None:
            return None
        same_dtype(left, right, mutations)
        result = operation(left, right)
        return checked_i64(result) if type(result) is int else result
    return apply


def ieee_div(left: float, right: float) -> float:
    """Apply IEEE 754 division; e.g. ``ieee_div(1.0, 0.0)`` returns infinity."""
    if right == 0.0:
        if left == 0.0 or math.isnan(left):
            return math.nan
        return math.copysign(math.inf, left) * math.copysign(1.0, right)
    return left / right


def div(left: object, right: object, mutations: Mutations) -> object:
    """Convert to F64 before division; e.g. ``div(5, 2)`` returns ``2.5``."""
    if left is None or right is None:
        return None
    if 'exact-quotient-div' in mutations and type(left) is int and type(right) is int and right != 0:
        return float(Fraction(left, right))
    return ieee_div(float(left), float(right))


def integer_quotient(left: object, right: object, mutations: Mutations) -> tuple[int, int] | None:
    """Return quotient and remainder; e.g. ``integer_quotient(-7, 2)`` gives ``(-3, -1)``."""
    if left is None or right is None:
        return None
    require(type(left) is int and type(right) is int, 'idiv and rem take I64 operands')
    if right == 0:
        raise SemanticFailure('DivisionByZero')
    if 'floor-idiv' in mutations:
        quotient = left // right
    else:
        quotient = abs(left) // abs(right) * (1 if (left < 0) == (right < 0) else -1)
    return checked_i64(quotient), left - right * quotient


def idiv(left: object, right: object, mutations: Mutations) -> object:
    """Truncate towards zero; e.g. idiv(-7, 2) is -3."""
    result = integer_quotient(left, right, mutations)
    return None if result is None else result[0]


def rem(left: object, right: object, mutations: Mutations) -> object:
    """Take the dividend's sign; e.g. rem(-7, 2) is -1."""
    result = integer_quotient(left, right, mutations)
    return None if result is None else result[1]


def extremum(pick_left: Callable[[object, object], bool], zero_sign: float) -> Callable[..., object]:
    """Build an IEEE extremum; e.g. minimum of ``-0.0`` and ``+0.0`` is ``-0.0``."""
    def apply(left: object, right: object, mutations: Mutations) -> object:
        """Apply the extremum rule; e.g. null paired with a value returns null."""
        if left is None or right is None:
            return None
        same_dtype(left, right, mutations)
        if isinstance(left, float) and (math.isnan(left) or math.isnan(right)):
            if 'nan-ignoring-min' in mutations:
                return right if math.isnan(left) else left
            return left if math.isnan(left) else right
        if isinstance(left, float) and left == right == 0.0:
            signs = {math.copysign(1.0, left), math.copysign(1.0, right)}
            return zero_sign if math.copysign(1.0, zero_sign) in signs else left
        return left if pick_left(left, right) else right
    return apply


def kleene(table: Callable[[bool, bool], bool], absorbing: bool | None) -> Callable[..., object]:
    """Build three-valued logic; e.g. false AND unknown is false."""
    def apply(left: object, right: object, mutations: Mutations) -> object:
        """Apply the truth table; e.g. false AND unknown returns false."""
        if 'two-valued-logic' in mutations:
            left, right = bool(left), bool(right)
        require(all(value is None or type(value) is bool for value in (left, right)), 'logic takes Bool operands')
        if absorbing is not None and absorbing in (left, right):
            return absorbing
        if left is None or right is None:
            return None
        return table(left, right)
    return apply


BINARY: dict[str, Callable[..., object]] = {
    'add': arithmetic(lambda left, right: left + right),
    'sub': arithmetic(lambda left, right: left - right),
    'mul': arithmetic(lambda left, right: left * right),
    'div': div, 'idiv': idiv, 'rem': rem,
    'min': extremum(lambda left, right: left < right, -0.0),
    'max': extremum(lambda left, right: left > right, 0.0),
    'and': kleene(lambda left, right: left and right, False),
    'or': kleene(lambda left, right: left or right, True),
    'xor': kleene(lambda left, right: left != right, None),
}


def cast(value: object, target: str) -> object:
    """Convert explicitly; e.g. ``cast(True, 'I64')`` returns ``1``."""
    if value is None or dtype(value) == target:
        return value
    if target == 'Bool':
        raise SemanticFailure('InvalidCast')
    if target == 'F64':
        return float(value)
    if type(value) is bool:
        return int(value)
    if not math.isfinite(value):
        raise SemanticFailure('NonFinite')
    if not value.is_integer():
        raise SemanticFailure('NonIntegral')
    if not I64_MIN <= value < 2.0**63:
        raise SemanticFailure('OutOfRange')
    return int(value)


AGGREGATES: dict[str, tuple[str, Callable[[str], object] | None]] = {
    'sum': ('add', lambda kind: 0.0 if kind == 'F64' else 0),
    'product': ('mul', lambda kind: 1.0 if kind == 'F64' else 1),
    'any': ('or', lambda kind: False),
    'all': ('and', lambda kind: True),
    'minimum': ('min', None),
    'maximum': ('max', None),
}


def right_reduce(name: str, values: list, mutations: Mutations) -> object:
    """Reduce with exact right association; e.g. sub over [10, 3, 2] yields 9."""
    if not values:
        raise SemanticFailure('EmptyReduction')
    operation = BINARY[name]
    if 'left-reduce' in mutations:
        result = values[0]
        for value in values[1:]:
            result = operation(result, value, mutations)
        return result
    result = values[-1]
    for value in reversed(values[:-1]):
        result = operation(value, result, mutations)
    return result


def left_fold(name: str, values: list, mutations: Mutations) -> object:
    """Fold with left association; e.g. sub over [10, 3, 2] yields 5."""
    if not values:
        raise SemanticFailure('EmptyReduction')
    operation = BINARY[name]
    result = values[0]
    for value in values[1:]:
        result = operation(result, value, mutations)
    return result


def null_policy(values: list, skip_nulls: bool) -> list | None:
    """Apply aggregate null policy; e.g. skip mode turns ``[1, None]`` into ``[1]``."""
    if skip_nulls:
        return [value for value in values if value is not None]
    return None if any(value is None for value in values) else values


def checked_identity(identity: object, element_dtype: str) -> object:
    """Require identity dtype agreement; e.g. ``checked_identity(0, 'I64')`` returns ``0``."""
    if dtype(identity) != element_dtype:
        raise SemanticFailure('IdentityDtype')
    return identity


def empty_result(name: str, case: dict, mutations: Mutations) -> object:
    """Return an empty aggregate result; e.g. an empty I64 sum is ``0``."""
    if 'identity' in case:
        return checked_identity(decode(case['identity']), 'F64' if name == 'mean' else case['dtype'])
    if name == 'mean':
        raise SemanticFailure('EmptyMean')
    registered = AGGREGATES[name][1]
    if registered is None or (name == 'sum' and 'empty-sum-error' in mutations):
        raise SemanticFailure('EmptyReduction')
    return registered(case['dtype'])


def aggregate(name: str, case: dict, mutations: Mutations) -> object:
    """Evaluate a whole-cell aggregate; e.g. ``sum([1, 2])`` returns ``3``."""
    if 'identity' in case:
        checked_identity(decode(case['identity']), 'F64' if name == 'mean' else case['dtype'])
    values = null_policy(decode(case['input']), case.get('skip_nulls', False))
    if values is None:
        return None
    if 'identity' in case and 'identity-as-seed' in mutations:
        values = [decode(case['identity'])] + values
    if not values:
        return empty_result(name, case, mutations)
    if name == 'mean':
        return ieee_div(right_reduce('add', [float(value) for value in values], mutations), float(len(values)))
    return right_reduce(AGGREGATES[name][0], values, mutations)


def variance(case: dict, mutations: Mutations) -> object:
    """Evaluate the declared two-pass variance; e.g. [1, 2, 3] with ddof 1 gives 1.0."""
    ddof = case.get('ddof', 0)
    if type(ddof) is not int or not 0 <= ddof <= I64_MAX:
        raise SemanticFailure('InvalidDegreesOfFreedom')
    values = null_policy(decode(case['input']), case.get('skip_nulls', False))
    if values is None:
        return None
    if any(type(value) not in {int, float} for value in values):
        raise SemanticFailure('DtypeMismatch')
    if len(values) > MEAN_COUNT_LIMIT:
        raise SemanticFailure('CountTooLarge')
    if len(values) <= ddof:
        raise SemanticFailure('InsufficientCount')

    f64_values = [float(value) for value in values]
    mean = ieee_div(right_reduce('add', f64_values, mutations), float(len(values)))
    if 'one-pass-variance' in mutations:
        squared_total = right_reduce('add', [value * value for value in f64_values], mutations)
        second_moment = ieee_div(squared_total, float(len(values)))
        result = second_moment - mean * mean
        return math.sqrt(result) if case['operation'] == 'stddev' else result
    deviations = [value - mean for value in f64_values]
    squared_deviations = [deviation * deviation for deviation in deviations]
    squared_total = right_reduce('add', squared_deviations, mutations)
    denominator = float(len(values) if 'ignore-ddof' in mutations else len(values) - ddof)
    result = ieee_div(squared_total, denominator)
    return math.sqrt(result) if case['operation'] == 'stddev' else result


def mean_count(case: dict, mutations: Mutations) -> object:
    """Admit exactly representable counts; e.g. ``2**53`` passes and ``2**53 + 1`` fails."""
    if case['count'] > MEAN_COUNT_LIMIT:
        raise SemanticFailure('CountTooLarge')
    return True


def batch_axis(case: dict, mutations: Mutations) -> object:
    """Count frame elements; e.g. shape ``[2, 3]`` has cardinality ``6``."""
    shape = case['shape']
    rank = len(shape) + (1 if 'cell-flattening' in mutations else 0)
    if not 0 <= case['axis'] < rank:
        raise SemanticFailure('AxisOutOfRange')
    return math.prod(shape)


def atomic_commit(case: dict, mutations: Mutations) -> object:
    """Commit all output or none; e.g. pre-commit failure preserves the destination."""
    destination, output, fail_at = list(case['destination']), case['output'], case['fail_at']
    if fail_at is None:
        return list(output)
    if 'partial-output' in mutations:
        destination[:fail_at] = output[:fail_at]
    return destination


def evaluate_contract(case: dict, mutations: Mutations = frozenset()) -> object:
    """Evaluate one contract case; e.g. ``idiv(-7, 2)`` gives ``-3``."""
    operation = case['operation']
    if operation in BINARY:
        left, right = decode(case['args'])
        return BINARY[operation](left, right, mutations)
    if operation == 'reduce':
        return right_reduce(case['binary'], decode(case['input']), mutations)
    if operation == 'fold_left':
        return left_fold(case['binary'], decode(case['input']), mutations)
    if operation == 'cast':
        return cast(decode(case['input']), case['to'])
    if operation in {'variance', 'stddev'}:
        return variance(case, mutations)
    if operation in AGGREGATES or operation == 'mean':
        return aggregate(operation, case, mutations)
    handlers = {'mean_count': mean_count, 'batch_axis': batch_axis, 'atomic_commit': atomic_commit}
    require(operation in handlers, f"Unknown contract operation {operation}")
    return handlers[operation](case, mutations)


def outcome(case: dict, mutations: Mutations = frozenset()) -> object:
    """Encode result or error; e.g. division by zero gives ``{'error': 'DivisionByZero'}``."""
    try:
        return encode(evaluate_contract(case, mutations))
    except SemanticFailure as error:
        return {'error': str(error)}


def expected_outcome(case: dict) -> object:
    """Normalize a recorded expectation; e.g. an expected error becomes its error mapping."""
    if 'expected_error' in case:
        return {'error': case['expected_error']}
    return encode(decode(case['expected']))


def check_contract_examples(context: ValidationContext) -> None:
    """Evaluate every contract example against its recorded expectation.

    Parameters
    ----------
    context : ValidationContext
        Repository root and cached specification documents.

    Raises
    ------
    AssertionError
        If an example is duplicated, malformed, or differs from the model.

    Examples
    --------
    A mismatched EX record fails validation with its identifier.
    """
    cases = context.load('spec/examples.json')['contract_cases']
    ids = [case['id'] for case in cases]
    require(len(ids) == len(set(ids)), 'Duplicate contract example ID')
    for case in cases:
        require(('expected' in case) != ('expected_error' in case), f"{case['id']} needs one expectation")
        actual = outcome(case)
        require(same_typed_value(actual, expected_outcome(case)),
                f"{case['id']} expected {expected_outcome(case)}, got {actual}")
    context.record('contract-examples', 'Tagged-scalar examples of the accepted numeric, validity, reduction, cell, and '
                                        'commit contracts evaluate as recorded in the documentation model.', len(cases))
