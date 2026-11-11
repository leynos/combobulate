"""Decide which crate owns a Rust source, and whether it expands literals (VO-9, VO-10).

DL-17 scans a string literal for trust vocabulary only when a macro could be
expanding it, and only a procedural-macro crate can do that. That is a property
of the crate, not of the source, so it is read from the crate's manifest — and
this module is the one place that reads it.

Ownership is the nearest ``Cargo.toml`` above a source. :func:`owning_manifest`
answers from the set of manifests the walk is allowed to trust rather than from
the working tree. A manifest deleted from disk still owns the sources it
compiled, so searching the filesystem would let such a manifest vanish and hand
its sources to a shallower crate that never compiled them. The shallower crate's
``[lib] proc-macro`` flag would then decide whether the sources' literals are
code, which is how a trust item silently leaves an audit that reports success.

Examples
--------
>>> is_procedural_macro_crate_text('[lib]\\nproc-macro = true\\n')
True
>>> is_procedural_macro_crate_text('[package]\\nname = "a"\\n')
False
"""
from __future__ import annotations

import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .lexer import TrustAuditError

MANIFEST_NAME = 'Cargo.toml'
# A proc-macro crate can turn a literal into code, so its literals are scanned.
# The manifest is parsed rather than pattern-matched because TOML gives an
# author many spellings of one declaration: `proc-macro=true`, a comment after
# the value, and the dotted `lib.proc-macro = true` all declare the same crate.
# Reading the text instead would audit any of them as an ordinary library and
# silently stop scanning the tokens that crate's macros emit.
PROCEDURAL_MACRO_TABLE = 'lib'
PROCEDURAL_MACRO_KEY = 'proc-macro'


@dataclass(frozen=True, slots=True)
class ManifestOwnership:
    """The manifest that owns one source file, and the bytes that decide its mode.

    ``path`` is repository-relative, so a refusal can name it and a
    working-tree read can resolve it against the root the audit was given.
    ``bound`` carries the manifest's verified bytes on a bound walk, and is None
    on the checkout walk, where the manifest is read from disk instead.
    """

    path: str
    bound: bytes | None


def tracked_manifests(root: Path) -> frozenset[str] | None:
    """List the ``Cargo.toml`` files Git tracks under ``root``, or None on failure.

    The index, not the filesystem, is what makes a *deleted* manifest visible.
    A bound walk that only looked on disk would find nothing above a source
    whose nested manifest the author had removed, fall through to the workspace
    root, and take that root's ordinary-crate answer for a proc-macro member's
    sources. The manifest is still tracked — it still compiled them — so the
    index reports it and the walk refuses instead.

    ``None`` means Git could not answer: outside a repository, without a Git
    executable, or after a command failure. The path-pattern form ``*Cargo.toml``
    is deliberate; ``:(glob)*Cargo.toml`` matches only the root manifest because
    the glob magic does not cross a directory separator.

    Parameters
    ----------
    root
        Repository root.

    Returns
    -------
    frozenset[str] | None
        Repository-relative manifest paths, or None when Git cannot say.

    Examples
    --------
    ``tracked_manifests(Path('/repo'))`` returns
    ``frozenset({'Cargo.toml', 'crates/macros/Cargo.toml'})`` for a workspace
    with one proc-macro member; a directory outside any repository returns None.
    """
    try:
        completed = subprocess.run(
            ['git', '-C', str(root), 'ls-files', '-z', '--', f'*{MANIFEST_NAME}'],
            capture_output=True, check=False, text=True)
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return frozenset(entry for entry in completed.stdout.split('\0') if entry)


def owning_manifest(root: Path, relative: str, bound: Mapping[str, bytes] | None,
                    tracked: frozenset[str] | None) -> ManifestOwnership | None:
    """Find the manifest owning ``relative``, or None when no crate compiles it.

    The nearest ancestor ``Cargo.toml`` owns the file. Which manifests count as
    present depends on the walk, because the two walks answer to different
    authorities.

    A checkout walk (``bound`` is None) reads the filesystem: a developer
    auditing a working tree wants the crate as it stands, and :func:`audit_tree`
    is also handed bare directories of ``.rs`` files whose only owner is what is
    on disk. No manifest anywhere is then the honest answer for a source no
    crate compiles, and the caller treats its literals as data.

    A bound walk may not read the filesystem for the answer, because a manifest
    whose bytes nobody verified must not decide anything. Its candidates are the
    bound manifests, plus any manifest Git tracks or the working tree still
    holds — presence in either is used only to *refuse*. That asymmetry is the
    point: an unbound manifest, deleted or not, can never silence literal
    scanning, but it can always stop the walk and name itself for the author to
    bind. A bound walk that finds no manifest at all refuses too, since "no
    crate" and "a crate whose manifest was not bound" are indistinguishable from
    verified bytes alone.

    Parameters
    ----------
    root
        Repository root.
    relative
        Repository-relative path of the source whose owner is wanted.
    bound
        Verified source bytes, or None for the checkout walk.
    tracked
        The manifests Git tracks, or None when unknown or irrelevant.

    Returns
    -------
    ManifestOwnership | None
        The owning manifest, or None when a checkout walk finds none.

    Raises
    ------
    TrustAuditError
        If the walk is bound and the owner is not one of its verified manifests,
        if no manifest owns a bound source at all, or if Git cannot report the
        manifests it tracks.

    Examples
    --------
    A bound walk holding ``src/lib.rs`` and ``Cargo.toml`` reports
    ``ManifestOwnership('Cargo.toml', b'[lib]\\nproc-macro = true\\n')``. The
    same walk with a tracked but unbound ``crates/m/Cargo.toml`` above the
    source refuses instead of falling through to the root.
    """
    if bound is None:
        return _checkout_owner(root, relative)
    return _bound_owner(root, relative, bound, tracked)


def is_procedural_macro_crate(manifest: Path) -> bool:
    """Report whether a crate's manifest declares a proc-macro target.

    The manifest is parsed as TOML and ``[lib] proc-macro`` is read from the
    document, rather than the directive being searched for in the text. TOML
    lets the same declaration be written with any spacing, with a trailing
    comment, or dotted as ``lib.proc-macro = true``; matching the text would
    read the last two as ordinary libraries. A false negative here is the
    unsound direction: the crate's literals are what its macros emit, so their
    vocabulary would go unreported.

    A manifest that cannot be read or parsed is *not* procedural, for the reason
    given at :func:`is_procedural_macro_crate_text`.

    Parameters
    ----------
    manifest
        Path to a ``Cargo.toml``.

    Returns
    -------
    bool
        True when the manifest declares ``[lib] proc-macro = true``.

    Examples
    --------
    A manifest containing ``[lib]`` and ``proc-macro = true`` returns True,
    including when the value carries a comment; an ordinary library manifest,
    a commented-out directive, and a missing file all return False.
    """
    try:
        text = manifest.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return False
    return is_procedural_macro_crate_text(text)


def is_procedural_macro_crate_text(text: str) -> bool:
    """Report whether manifest *text* declares a proc-macro target.

    This is the decision :func:`is_procedural_macro_crate` makes once it has
    read a file, exposed separately so the bound walk can decide from the bytes
    a record's digest vouched for rather than re-opening the path. A manifest
    that does not parse is not procedural: describing it as one would scan an
    ordinary crate's data as code, reporting trust items the author never
    wrote.

    Parameters
    ----------
    text
        The manifest's contents, as TOML.

    Returns
    -------
    bool
        True when the document declares ``[lib] proc-macro = true``.

    Examples
    --------
    >>> is_procedural_macro_crate_text('[lib]\\nproc-macro = true\\n')
    True
    >>> is_procedural_macro_crate_text('[package]\\nname = "a"\\n')
    False
    """
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return False
    library = document.get(PROCEDURAL_MACRO_TABLE)
    return isinstance(library, Mapping) and library.get(PROCEDURAL_MACRO_KEY) is True


def _checkout_owner(root: Path, relative: str) -> ManifestOwnership | None:
    """Return the nearest manifest the working tree holds, if there is one."""
    for path in _candidate_paths(relative):
        if (root / path).is_file():
            return ManifestOwnership(path, None)
    return None


def _bound_owner(root: Path, relative: str, bound: Mapping[str, bytes],
                 tracked: frozenset[str] | None) -> ManifestOwnership | None:
    """Return the owning manifest from verified bytes, refusing anything else.

    The nearest manifest decides, so the candidates are walked nearest first and
    the first one that exists at all ends the search: either it is bound and its
    bytes answer, or it is unbound and the walk refuses rather than reaching for
    a shallower crate that does not own the file.

    Reaching the end means no manifest exists above the source. That is only a
    fact when Git answered the index question; without it, a manifest deleted
    from disk is indistinguishable from one that never existed, and the two
    carry opposite answers, so the walk refuses.
    """
    for path in _candidate_paths(relative):
        if path in bound:
            return ManifestOwnership(path, bound[path])
        if _is_present(root, path, tracked):
            raise TrustAuditError(
                f'{relative}: its crate manifest {path} is not bound to a digest, so whether '
                f'the crate expands literals cannot be verified')
    if tracked is None:
        raise TrustAuditError(
            f'{relative}: Git cannot report the manifests it tracks, so whether a crate owns '
            f'this source cannot be verified')
    return None


def _is_present(root: Path, path: str, tracked: frozenset[str] | None) -> bool:
    """Report whether a manifest exists for this audit, on disk or in the index.

    Both answers only ever cause a refusal, so reading the working tree here
    cannot hide anything; a deleted manifest is caught by the index instead.
    """
    return (tracked is not None and path in tracked) or (root / path).is_file()


def _candidate_paths(relative: str) -> tuple[str, ...]:
    """Return the manifest paths above ``relative``, nearest first.

    ``PurePosixPath`` is used so the answer is the repository-relative path the
    rest of the walk speaks, without depending on the host separator.
    """
    directories = [PurePosixPath(relative).parent]
    while directories[-1] != PurePosixPath('.'):
        directories.append(directories[-1].parent)
    return tuple(MANIFEST_NAME if directory == PurePosixPath('.')
                 else (directory / MANIFEST_NAME).as_posix()
                 for directory in directories)
