"""Confine Polars paths to the backend module they belong to (VO-14).

DL-19 keeps the Polars adapter inside a crate-private facade module rather than
in a crate of its own, and VO-14 is what holds that separation in place: Polars
paths may appear in ``src/polars_backend.rs`` and its submodules, and nowhere
else in the facade.

The rule is checked with the trust-audit lexer, so a ``polars::`` inside a
comment or a string literal is not a violation — it is not compiled, and a doc
comment that mentions Polars is exactly what a confined module's own docs look
like. Only real code counts.

Non-vacuity is part of the control: a seeded ``use polars::`` in a copy of
``src/profile.rs`` must be reported. Without that half, a check that had
regressed to reporting nothing would still pass, and every later confinement
claim would be unsupported.
"""
from __future__ import annotations

from pathlib import Path

from .context import ValidationContext, require
from .trust_audit import Kind, Token, TrustAuditError, alias_bindings, tokenize

# The one module allowed to name Polars, and the only prefix its submodules
# could take. A submodule of the backend is still the backend.
BACKEND_MODULE = 'src/polars_backend.rs'
BACKEND_PREFIX = 'src/polars_backend/'
# The crate root's token stream is where a confinement violation is most
# likely, because that is where the facade's public surface is declared.
NON_VACUITY_SOURCE = 'src/profile.rs'
POLARS_PATH = 'polars'
PATH_SEPARATOR = '::'
RUST_SUFFIX = '.rs'


def check_polars_confinement(context: ValidationContext) -> None:
    """Require Polars paths to stay inside the backend module.

    Parameters
    ----------
    context
        Repository inputs owned by the documentation checker.

    Returns
    -------
    None
        Records one result for the Polars confinement check.

    Raises
    ------
    AssertionError
        If a Polars path appears outside the backend module, or the seeded
        violation in a copy of the facade is not reported.
    TrustAuditError
        If a facade source cannot be tokenized; the check fails closed rather
        than reporting an empty scan.

    Examples
    --------
    ``check_polars_confinement(context)`` passes when only
    ``src/polars_backend.rs`` reaches Polars, and fails listing the file and
    position of any other occurrence.
    """
    violations = _violations(context.root)
    require(not violations,
            'Polars paths must stay inside '
            f'{BACKEND_MODULE}; found ' + ', '.join(violations))
    _require_seeded_violation(context.root)
    context.record('polars-confinement',
                   f'Polars paths appear only in {BACKEND_MODULE}; a seeded '
                   'violation in a copy of the facade is still reported.',
                   len(_facade_sources(context.root)))


def _violations(root: Path) -> list[str]:
    """Return every Polars path outside the backend module, with its position."""
    found = []
    for source in _facade_sources(root):
        relative = source.relative_to(root).as_posix()
        if _is_backend(relative):
            continue
        found.extend(f'{relative}:{token.line}:{token.column}'
                     for token in _polars_paths(source.read_text(encoding='utf-8')))
    return found


def _is_backend(relative: str) -> bool:
    """Report whether a facade source belongs to the backend module."""
    return relative == BACKEND_MODULE or relative.startswith(BACKEND_PREFIX)


def _facade_sources(root: Path) -> tuple[Path, ...]:
    """Return every Rust source in the facade's ``src`` tree.

    The walk is rooted at the facade's own ``src`` rather than at the whole
    repository, because the other workspace members are separate crates with
    their own confinement questions. A directory that does not exist yet is not
    an error: the facade's shape is a deliverable of later tasks, and this check
    must keep working while the tree grows.
    """
    src = root / 'src'
    if not src.is_dir():
        return ()
    return tuple(sorted(src.rglob(f'*{RUST_SUFFIX}')))


def _polars_paths(text: str) -> list[Token]:
    """Return the tokens that begin a path into the Polars crate.

    A bare ``polars`` identifier that is not followed by ``::`` is not a path
    into the crate: it is how the module is named, imported, or referred to in
    prose the lexer has already discarded. Only the qualified form reaches the
    dependency's items, so only that form is confined.

    The path need not be spelled ``polars::``. ``use polars as p;`` binds the
    crate to another name — the same renaming the trust audit resolves for its
    own roots — after which ``p::prelude::DataFrame`` reaches exactly the items
    the literal form does. Matching only the literal spelling would let a facade
    module import Polars under any name it liked and still pass the control,
    which is the failure DL-19 keeps the confinement rule for. A grouped
    ``use polars::{self as p};`` is the same rename and is read the same way.
    """
    tokens = tokenize(text)
    names = alias_bindings(tokens, POLARS_PATH)
    return [
        token
        for index, token in enumerate(tokens)
        if token.kind is Kind.IDENT
        and token.text in names
        and index + 1 < len(tokens)
        and tokens[index + 1].text == PATH_SEPARATOR
    ]


def _require_seeded_violation(root: Path) -> None:
    """Require a seeded ``use polars::`` in a copy of the facade to be reported.

    The copy is tokenized in memory rather than written beside the real source,
    so the control cannot leave a stray file behind if it fails, and it cannot
    be confused with the real facade by any later walk.

    The seeded text is handed to :func:`_polars_paths`, the detector the real
    walk uses, rather than to a second reader written for the control. A control
    that searched for the literal word with its own predicate would keep firing
    after the detector regressed — the very case the control exists to catch.
    """
    original = root / NON_VACUITY_SOURCE
    require(original.is_file(), f'the non-vacuity control needs {NON_VACUITY_SOURCE} to exist')
    seeded = f'use {POLARS_PATH}::prelude::DataFrame;\n' + original.read_text(encoding='utf-8')
    require(_polars_paths(seeded),
            'a seeded `use polars::` in a copy of '
            f'{NON_VACUITY_SOURCE} must be reported, so a scan that found '
            'nothing anywhere cannot pass')


__all__ = ['BACKEND_MODULE', 'check_polars_confinement']
