"""Locate bracketed groups in a lexed Rust source (DL-17).

Both halves of the audit walk brackets. The matcher needs an attribute's span to
decide whether it carries Verus vocabulary, and it needs a ``verus!`` body's
span to bound the region; the module walker needs the span to read a
``#[path = "…"]`` value. The two searches must agree about which ``]`` closes
which ``[``, because an attribute read one token short silently moves the
region it names.

Keeping the bracket arithmetic in one module means neither caller can drift
from the other. The helpers take token tuples and indices rather than any
source text, so they are testable without a lexer run and cost nothing beyond
the tokens already produced.
"""
from __future__ import annotations

from .lexer import Kind, Token, TrustAuditError, literal_body


def matching(tokens: tuple[Token, ...], open_index: int, opener: str, closer: str) -> int:
    """Return the index of the token closing the group opened at ``open_index``.

    Examples
    --------
    For tokens ``( verus! { x } )``, ``matching`` on the ``{`` reports the ``}``.
    """
    depth = 0
    for index in range(open_index, len(tokens)):
        if tokens[index].text == opener:
            depth += 1
        elif tokens[index].text == closer:
            depth -= 1
            if depth == 0:
                return index
    raise TrustAuditError(
        f'unclosed {opener!r} opened at line {tokens[open_index].line}, '
        f'column {tokens[open_index].column}'
    )


def attribute_spans(tokens: tuple[Token, ...]) -> tuple[tuple[int, int], ...]:
    """Return ``(open, close)`` bracket indices for every attribute.

    Both forms are ordinary attributes for this purpose: ``#[cfg_attr(...)]``
    and ``#![cfg_attr(...)]`` carry a Verus attribute equally well. Reading a
    span from the wrong bracket would make every attribute one token short, so
    the outer and inner forms are distinguished explicitly rather than by
    skipping one of them.
    """
    spans = []
    for index, token in enumerate(tokens):
        if token.text != '#':
            continue
        inner = index + 1 < len(tokens) and tokens[index + 1].text == '!'
        opening = index + 2 if inner else index + 1
        if opening < len(tokens) and tokens[opening].text == '[':
            spans.append((opening, matching(tokens, opening, '[', ']')))
    return tuple(spans)


def previous_closer(tokens: tuple[Token, ...], opener: int) -> int:
    """Return the index of the ``]`` closing the attribute before ``opener``, or -1.

    Searching backwards rather than stepping a fixed distance keeps the walk
    correct for both ``#[…]`` and ``#![…]``: the two forms differ by one token
    at the front, and an offset calibrated for one is off by one for the other.
    """
    for index in range(opener - 1, -1, -1):
        if tokens[index].text == ']':
            return index
        if tokens[index].text not in ('#', '!'):
            return -1
    return -1


def skip_visibility(tokens: tuple[Token, ...], index: int) -> int:
    """Step backwards over ``pub`` or ``pub(…)`` and return the index before it.

    ``pub(in path)`` and ``pub(crate)`` are handled by skipping the matching
    parentheses, so the four visibility forms need no separate cases.
    """
    if index >= 0 and tokens[index].text == ')':
        opener = opening_paren(tokens, index)
        if opener is None or opener < 1 or tokens[opener - 1].text != 'pub':
            return index
        return opener - 2
    return index - 1 if index >= 0 and tokens[index].text == 'pub' else index


def opening_paren(tokens: tuple[Token, ...], close_index: int) -> int | None:
    """Return the index of the ``(`` matching the ``)`` at ``close_index``."""
    depth = 0
    for index in range(close_index, -1, -1):
        if tokens[index].text == ')':
            depth += 1
        elif tokens[index].text == '(':
            depth -= 1
            if depth == 0:
                return index
    return None


def opening_bracket(tokens: tuple[Token, ...], close_index: int) -> int | None:
    """Return the index of the ``[`` matching the ``]`` at ``close_index``."""
    depth = 0
    for index in range(close_index, -1, -1):
        if tokens[index].text == ']':
            depth += 1
        elif tokens[index].text == '[':
            depth -= 1
            if depth == 0:
                return index
    return None


def path_value(tokens: tuple[Token, ...], open_index: int, close_index: int) -> str | None:
    """Return the value of a ``#[path = "…"]`` span, if it is one."""
    head = tokens[open_index + 1:open_index + 3]
    if len(head) != 2 or head[0].text != 'path' or head[1].text != '=':
        return None
    if close_index <= open_index + 3:
        return None
    literal = tokens[open_index + 3]
    return literal_body(literal.text)[1] if literal.kind is Kind.LITERAL else None
