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

from .context import ValidationContext, require
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
    """Name a scalar's dtype; Bool is not an integer subtype, and null has none."""
    if value is None:
        return None
    return {bool: 'Bool', int: 'I64', float: 'F64'}[type(value)]


def same_dtype(left: object, right: object, mutations: Mutations) -> None:
    """Reject mixed operands; the 'implicit-promotion' mutation silently widens instead."""
    if dtype(left) != dtype(right) and 'implicit-promotion' not in mutations:
        raise SemanticFailure('DtypeMismatch')


def checked_i64(value: int) -> int:
    """Reject results outside I64."""
    if not I64_MIN <= value <= I64_MAX:
        raise SemanticFailure('IntegerOverflow')
    return value


def arithmetic(operation: Callable[[object, object], object]) -> Callable[..., object]:
    """Lift an operation to null-propagating, same-dtype, checked-I64 arithmetic."""
    def apply(left: object, right: object, mutations: Mutations) -> object:
        if left is None or right is None:
            return None
        same_dtype(left, right, mutations)
        result = operation(left, right)
        return checked_i64(result) if type(result) is int else result
    return apply


def ieee_div(left: float, right: float) -> float:
    """IEEE 754 division, including zero divisors; Python's own division raises instead."""
    if right == 0.0:
        if left == 0.0 or math.isnan(left):
            return math.nan
        return math.copysign(math.inf, left) * math.copysign(1.0, right)
    return left / right


def div(left: object, right: object, mutations: Mutations) -> object:
    """Convert each operand to F64 with ties-to-even, then divide (D14)."""
    if left is None or right is None:
        return None
    if 'exact-quotient-div' in mutations and type(left) is int and type(right) is int and right != 0:
        return float(Fraction(left, right))
    return ieee_div(float(left), float(right))


def integer_quotient(left: object, right: object, mutations: Mutations) -> tuple[int, int] | None:
    """Return the truncating quotient and remainder; zero and MIN/-1 fail."""
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
    """Build IEEE 754-2019 minimum or maximum: null first, then NaN, then signed-zero ties (D09)."""
    def apply(left: object, right: object, mutations: Mutations) -> object:
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
    """Build three-valued logic; an absorbing operand decides the result even beside unknown."""
    def apply(left: object, right: object, mutations: Mutations) -> object:
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
    """Convert explicitly (V031): Bool to 0/1, I64 to F64 with ties-to-even, checked F64 to I64."""
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
    """Reduce with exact right association; a singleton passes through unchanged."""
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


def null_policy(values: list, skip_nulls: bool) -> list | None:
    """Apply the aggregate null policy first: propagate by default, or drop invalid values in order."""
    if skip_nulls:
        return [value for value in values if value is not None]
    return None if any(value is None for value in values) else values


def checked_identity(identity: object, element_dtype: str) -> object:
    """Require an explicit identity to match the output dtype."""
    if dtype(identity) != element_dtype:
        raise SemanticFailure('IdentityDtype')
    return identity


def empty_result(name: str, case: dict, mutations: Mutations) -> object:
    """Return an aggregate's empty-lane result; identities are never seeds."""
    if name == 'mean':
        raise SemanticFailure('EmptyMean')
    if 'identity' in case:
        return checked_identity(decode(case['identity']), case['dtype'])
    registered = AGGREGATES[name][1]
    if registered is None or (name == 'sum' and 'empty-sum-error' in mutations):
        raise SemanticFailure('EmptyReduction')
    return registered(case['dtype'])


def aggregate(name: str, case: dict, mutations: Mutations) -> object:
    """Evaluate one whole-cell aggregate (V058 to V064) over a rank-one input."""
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


def mean_count(case: dict, mutations: Mutations) -> object:
    """Admit a mean count up to and including 2^53, the exact count-conversion range (D09)."""
    if case['count'] > MEAN_COUNT_LIMIT:
        raise SemanticFailure('CountTooLarge')
    return True


def batch_axis(case: dict, mutations: Mutations) -> object:
    """Treat each typed cell as one element (D10): cardinality excludes components, axes index the frame."""
    shape = case['shape']
    rank = len(shape) + (1 if 'cell-flattening' in mutations else 0)
    if case['axis'] >= rank:
        raise SemanticFailure('AxisOutOfRange')
    return math.prod(shape)


def atomic_commit(case: dict, mutations: Mutations) -> object:
    """Return the destination after a commit; failure before commit leaves it unchanged (D10)."""
    destination, output, fail_at = list(case['destination']), case['output'], case['fail_at']
    if fail_at is None:
        return list(output)
    if 'partial-output' in mutations:
        destination[:fail_at] = output[:fail_at]
    return destination


def evaluate_contract(case: dict, mutations: Mutations = frozenset()) -> object:
    """Evaluate one contract example; e.g. {'operation': 'idiv', 'args': [-7, 2]} gives -3."""
    operation = case['operation']
    if operation in BINARY:
        left, right = decode(case['args'])
        return BINARY[operation](left, right, mutations)
    if operation == 'reduce':
        return right_reduce(case['binary'], decode(case['input']), mutations)
    if operation == 'cast':
        return cast(decode(case['input']), case['to'])
    if operation in AGGREGATES or operation == 'mean':
        return aggregate(operation, case, mutations)
    handlers = {'mean_count': mean_count, 'batch_axis': batch_axis, 'atomic_commit': atomic_commit}
    require(operation in handlers, f"Unknown contract operation {operation}")
    return handlers[operation](case, mutations)


def outcome(case: dict, mutations: Mutations = frozenset()) -> object:
    """Return an encoded result or {'error': name}, so outcomes compare exactly."""
    try:
        return encode(evaluate_contract(case, mutations))
    except SemanticFailure as error:
        return {'error': str(error)}


def expected_outcome(case: dict) -> object:
    """Normalize a case's expectation to the shape `outcome` returns."""
    if 'expected_error' in case:
        return {'error': case['expected_error']}
    return encode(decode(case['expected']))


def check_contract_examples(context: ValidationContext) -> None:
    """Evaluate every contract example and require each to match its expectation."""
    cases = context.load('spec/examples.json')['contract_cases']
    ids = [case['id'] for case in cases]
    require(len(ids) == len(set(ids)), 'Duplicate contract example ID')
    for case in cases:
        require(('expected' in case) != ('expected_error' in case), f"{case['id']} needs one expectation")
        actual = outcome(case)
        require(actual == expected_outcome(case), f"{case['id']} expected {expected_outcome(case)}, got {actual}")
    context.record('contract-examples', 'Tagged-scalar examples of the accepted numeric, validity, reduction, cell, and '
                                        'commit contracts evaluate as recorded in the documentation model.', len(cases))
