"""Read the ``use`` statements that decide a trust root's local names (DL-17).

The trust audit answers one question: *which names in this file reach a
verifier's trust surface?* ADR-0009 and DL-17 root that question in a crate —
``kani``, ``vstd``, ``verus_builtin`` — but a Rust file need not spell the crate
at the use site. Three forms change what a name refers to:

- ``use kani::assume;`` binds a *name*, so a bare ``assume(..)`` later in the
  file is the Kani call even without the ``kani::`` prefix.
- ``use kani as k;`` binds the *crate* under another name, so ``k::assume`` is
  the same qualified path as ``kani::assume``.
- ``use kani::*;`` binds whatever the crate exports, and is treated the same
  way as the named form for the fail-closed reason the matcher states.

The helpers here are deliberately narrow: they locate the statement, its root,
and an optional alias. Deciding what a binding *means* belongs to
:mod:`docs_validation.trust_audit.matcher`, which owns the vocabulary; this
module only reports what the source says.
"""
from __future__ import annotations

from .lexer import Kind, Token


def alias_bindings(tokens: tuple[Token, ...], root: str) -> frozenset[str]:
    """Return every local name a file binds ``root`` to, plus ``root`` itself.

    Rust lets a crate be renamed on import — ``use kani as k;`` — after which
    ``k::assume`` is the same call as ``kani::assume``. The audit's location
    claim is about what the code does, not what the crate is called at the use
    site, so an alias is matched exactly like the literal root.

    Only the single-name form is read. A grouped or glob import
    (``use kani::{assume};``, ``use kani::*;``) binds items rather than the
    crate, so the qualified-path rule does not apply to it.

    Examples
    --------
    A file that renames the crate reports both names::

        alias_bindings(tokenize('use kani as k;'), 'kani')  # {'kani', 'k'}
    """
    names = {root}
    for index, token in enumerate(tokens):
        if token.kind is not Kind.IDENT or token.text != 'use':
            continue
        end = statement_end(tokens, index + 1)
        if use_root(tokens, index + 1) != root:
            continue
        alias = use_alias(tokens, index + 1, end)
        if alias is not None:
            names.add(alias)
    return frozenset(names)


def use_alias(tokens: tuple[Token, ...], start: int, end: int) -> str | None:
    """Return the name in ``use root as name;``, or None for any other form.

    The ``as`` must be the statement's own, so a grouped import whose last
    member is renamed does not rename the crate. Reaching a brace before ``as``
    means the statement binds something else.
    """
    for index in range(start, end):
        text = tokens[index].text
        if text in {'{', '}'}:
            return None
        if text == 'as':
            alias = tokens[index + 1] if index + 1 < end else None
            return alias.text if alias is not None and alias.kind is Kind.IDENT else None
    return None


def use_root(tokens: tuple[Token, ...], start: int) -> str | None:
    """Return the crate a ``use`` statement takes its paths from.

    A leading ``::`` means an absolute path, so the root is the first identifier
    after it. Anything else is the first identifier in the statement.
    """
    for index in range(start, statement_end(tokens, start)):
        token = tokens[index]
        if token.kind is Kind.IDENT:
            return token.text
    return None


def statement_end(tokens: tuple[Token, ...], start: int) -> int:
    """Return the index of the ``;`` closing the statement opened at ``start``."""
    for index in range(start, len(tokens)):
        if tokens[index].text == ';':
            return index
    return len(tokens)
