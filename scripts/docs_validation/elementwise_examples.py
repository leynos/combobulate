"""Evaluate the SC-12 examples that pin down checked elementwise I64 addition.

This is a documentation model of the semantic contract, not the Rust
implementation. It states the two facts SC-12 has to fix executably: which
static failure a pair of operand lengths produces, and where a dynamic
overflow is reported. `contract_examples.py` dispatches the `elementwise_add`
operation here, so the examples are checked by the same path as every other
registered contract.

The model works on whole vectors rather than rows because this contract is
rank-one only, and it names the least overflowing position because the Rust
kernel and the Verus contract both report that position and nothing else.
"""
from __future__ import annotations

from collections.abc import Callable

from .context import require
from .scalar_codec import decode
from .semantics import SemanticFailure

I64_MIN, I64_MAX = -(2**63), 2**63 - 1
Mutations = frozenset[str]
AddOperation = Callable[[int, int], int]


def checked_add(left: int, right: int) -> int:
    """Add two I64 values, rejecting a result outside the dtype.

    For example, adding ``1`` to ``2**63 - 1`` raises ``IntegerOverflow``.
    """
    result = left + right
    if not I64_MIN <= result <= I64_MAX:
        raise SemanticFailure('IntegerOverflow')
    return result


def wrapping_add(left: int, right: int) -> int:
    """Add two I64 values modulo ``2**64``; the seeded mutant's arithmetic.

    For example, wrapping ``2**63 - 1`` and ``1`` gives ``-2**63``.
    """
    return (left + right - I64_MIN) % (2**64) + I64_MIN


def addition(mutations: Mutations) -> AddOperation:
    """Select the arithmetic; e.g. the ``wrapping-add`` mutation wraps instead of failing."""
    return wrapping_add if 'wrapping-add' in mutations else checked_add


def operand_vectors(case: dict) -> tuple[list[int], list[int]]:
    """Decode the two tagged operands; e.g. an ``i64`` tag becomes a Python ``int``.

    Wide I64 values are tagged so they survive JSON, so the operands go through
    the shared scalar decoder before the model sees them.
    """
    left, right = (decode(operand) for operand in case['args'])
    for operand in (left, right):
        require(all(type(value) is int and I64_MIN <= value <= I64_MAX for value in operand),
                f"{case['id']} operands must be I64 vectors")
    return left, right


def add_vectors(left: list[int], right: list[int], mutations: Mutations) -> list[int]:
    """Add equal-length vectors elementwise, failing at the least overflowing position.

    For example, ``[0, 2**63 - 1]`` plus ``[0, 1]`` reports position 1, not 0,
    because position 0 does not overflow and the contract names the first one
    that does.
    """
    require(len(left) == len(right), 'elementwise addition requires equal lengths')
    operation = addition(mutations)
    sums: list[int] = []
    for position, (lhs, rhs) in enumerate(zip(left, right)):
        try:
            sums.append(operation(lhs, rhs))
        except SemanticFailure as error:
            raise SemanticFailure(f'{error} at position {position}') from error
    return sums


def elementwise_add(case: dict, mutations: Mutations) -> list[int]:
    """Evaluate one SC-12 case; e.g. ``[1, 2, 3]`` plus ``[10, 20, 30]`` gives ``[11, 22, 33]``.

    A length disagreement fails before any element is examined, which is what
    makes it a preparation failure rather than an execution one.
    """
    left, right = operand_vectors(case)
    if len(left) != len(right):
        raise SemanticFailure('ShapeAgreement')
    return add_vectors(left, right, mutations)
