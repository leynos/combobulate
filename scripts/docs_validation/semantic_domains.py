"""Validate documentation-model operands before Python can coerce their domains.

Shape and policy boundaries belong to the semantic models, including direct
helper calls. These checks reject malformed examples; they do not model a Rust
runtime error or replace the expected-error cases in the design ledger.
"""
from __future__ import annotations

from .context import require


def validate_shape(shape: object) -> None:
    """Require array dimensions; [] and [0, 3] pass, while [True] and [-1] fail."""
    require(isinstance(shape, list), 'Malformed shape: expected a dimension list')
    require(all(type(dimension) is int and dimension >= 0 for dimension in shape),
            'Malformed shape: expected nonnegative integer dimensions')


def validate_boolean(value: object, name: str) -> None:
    """Require a policy boolean; False passes, while 'false' and 0 fail."""
    require(type(value) is bool, f'Malformed {name}: expected a boolean')


def validate_i64(value: object) -> None:
    """Require an I64 operand; -2**63 passes, while 2**63, True, and 1.0 fail."""
    require(type(value) is int and -(2**63) <= value < 2**63, 'Malformed I64 operand')


def validate_i64_values(values: object) -> None:
    """Validate a checked-add input sequence; [] remains a valid empty reduction."""
    require(isinstance(values, list), 'Malformed I64 input: expected a list')
    for value in values:
        validate_i64(value)


def validate_integer_values(values: object, nullable: bool = False) -> None:
    """Require model I64 values; optional nulls never permit booleans or floats."""
    require(isinstance(values, list), 'Malformed integer input: expected a list')
    require(all(type(value) is int or (nullable and value is None) for value in values),
            'Malformed integer operand')
    for value in values:
        if value is not None:
            validate_i64(value)


def validate_subtraction(case: dict) -> None:
    """Validate the supported subtraction examples; operation='suub' fails."""
    require(case.get('operation') == 'sub', f'Unknown subtraction operation {case.get("operation")}')
    validate_integer_values(case['input'])


def validate_board(board: object) -> None:
    """Require a rectangular board; [] and [[], []] pass, while [[1], [1, 2]] fails."""
    require(isinstance(board, list), 'Malformed board: expected a row list')
    require(all(isinstance(row, list) for row in board), 'Malformed board: expected row lists')
    if board:
        require(all(len(row) == len(board[0]) for row in board), 'Malformed board: rows must be rectangular')
    for row in board:
        validate_integer_values(row)
