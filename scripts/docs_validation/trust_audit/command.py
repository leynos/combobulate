"""Audit a repository tree for trusted items, resolving what the lexer cannot (VO-9, VO-10).

:mod:`docs_validation.trust_audit.matcher` decides what one source file
contains. This module supplies the two things a single file does not have: a
repository root, which turns a ``mod`` declaration into a real target, and a set
of files, which turns one scan into an audit.

Two policies live here rather than in the matcher, because both need that root:

- A module target outside the repository is refused. Following it would audit a
  file the repository does not own, and skipping it would silently exclude code
  that *is* compiled into the crate.
- The walk follows ``mod`` declarations rather than sweeping every ``.rs`` file
  in a directory. A file no ``mod`` names is not compiled, so scanning it would
  report items in dead code as though they were part of the proof.

The output shape is ``spec/proof-evidence.schema.json``'s ``trust_audit.items``:
one object per item with ``item``, ``location``, and ``covered_by``. The
scanner cannot know which assumption covers an item — that is the record
author's claim — so it reports ``covered_by`` as null and the gate compares the
result with the record.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .lexer import TrustAuditError
from .matcher import ModuleReference, ScanResult, TrustItem, scan

RUST_SUFFIX = '.rs'
# A proc-macro crate can turn a literal into code, so its literals are scanned.
PROCEDURAL_MACRO_DIRECTIVE = 'proc-macro = true'
# The file a bare `mod x;` resolves to inside a `src/`-style module.
MODULE_FILE_CANDIDATES = ('{directory}/{name}{suffix}', '{directory}/{name}/mod{suffix}')


@dataclass(frozen=True, slots=True)
class AuditedFile:
    """One scanned file, with the repository-relative path its items belong to."""

    path: str
    items: tuple[TrustItem, ...]


def audit_tree(root: Path, drivers: Iterable[str]) -> tuple[AuditedFile, ...]:
    """Audit every Rust source reachable from the given entry points.

    Parameters
    ----------
    root
        Repository root; every scanned file must resolve inside it.
    drivers
        Repository-relative Rust files to start from, typically each crate's
        ``lib.rs``, ``main.rs``, and integration-test roots.

    Returns
    -------
    tuple[AuditedFile, ...]
        One entry per scanned file that contains at least one item, in path
        order so an audit is stable across platforms and runs.

    Raises
    ------
    TrustAuditError
        If a driver is missing, a module target leaves the repository or does
        not exist, or a file cannot be scanned.

    Examples
    --------
    audit_tree(root, ['src/lib.rs']) returns every item in the crate's module
    tree, not only the ones written in ``src/lib.rs``.
    """
    scanned: dict[str, tuple[TrustItem, ...]] = {}
    pending = list(dict.fromkeys(drivers))
    while pending:
        relative = PurePosixPath(pending.pop().replace('\\', '/')).as_posix()
        if relative in scanned:
            continue
        result = _scan_file(root, relative)
        scanned[relative] = result.items
        pending.extend(_module_targets(root, relative, result.modules))
    return tuple(AuditedFile(path, scanned[path])
                 for path in sorted(scanned) if scanned[path])


def items_of(files: Iterable[AuditedFile]) -> tuple[Mapping[str, str | None], ...]:
    """Render items in the schema's ``trust_audit.items`` shape.

    Parameters
    ----------
    files
        Audited files, as returned by :func:`audit_tree`.

    Returns
    -------
    tuple[Mapping[str, str | None], ...]
        One ``{'item', 'location', 'covered_by'}`` object per item, with the
        location written as ``path:line:column``.

    Examples
    --------
    items_of([AuditedFile('src/lib.rs', (TrustItem('assume', 3, 5),))]) yields
    ``{'item': 'assume', 'location': 'src/lib.rs:3:5', 'covered_by': None}``.
    """
    return tuple({'item': item.item, 'location': f'{file.path}:{item.line}:{item.column}',
                  'covered_by': None}
                 for file in files for item in file.items)


def scan_tree(root: Path, relative: str, procedural_macro: bool = False) -> ScanResult:
    """Scan one repository-relative file, failing closed if it is absent.

    Parameters
    ----------
    root
        Repository root; ``relative`` resolves beneath it and may not escape.
    relative
        Repository-relative path to a Rust source.
    procedural_macro
        Scan literals too, for a crate that expands them into code.

    Returns
    -------
    ScanResult
        The file's items and any module files it compiles.

    Raises
    ------
    TrustAuditError
        If the path is absolute, escapes the root, or cannot be read.

    Examples
    --------
    scan_tree(root, 'src/lib.rs') reads ``root/src/lib.rs`` and reports what it
    contains; scan_tree(root, '../../etc/passwd') is refused.
    """
    path = resolve_repository_path(root, relative)
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as error:
        raise TrustAuditError(f'{relative} cannot be read: {error}') from error
    return scan(text, procedural_macro=procedural_macro)


def is_procedural_macro_crate(manifest: Path) -> bool:
    """Report whether a crate's manifest declares a proc-macro target.

    Parameters
    ----------
    manifest
        Path to a ``Cargo.toml``.

    Returns
    -------
    bool
        True when the manifest declares ``proc-macro = true``.

    Examples
    --------
    A manifest containing ``[lib]`` and ``proc-macro = true`` returns True; an
    ordinary library manifest returns False.
    """
    try:
        return PROCEDURAL_MACRO_DIRECTIVE in manifest.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return False


def resolve_repository_path(root: Path, relative: str) -> Path:
    """Resolve a repository-relative path, refusing anything outside the root.

    Containment is checked on the resolved path, so ``a/../../b`` cannot borrow
    the root's prefix to escape it.

    Parameters
    ----------
    root
        Repository root.
    relative
        Repository-relative path.

    Returns
    -------
    Path
        The resolved absolute path.

    Raises
    ------
    TrustAuditError
        If ``relative`` is absolute or resolves outside ``root``.

    Examples
    --------
    resolve_repository_path(root, 'src/lib.rs') returns root/src/lib.rs;
    resolve_repository_path(root, '../elsewhere.rs') is refused.
    """
    if PurePosixPath(relative).is_absolute():
        raise TrustAuditError(f'{relative} is absolute; the audit reads only repository files')
    resolved = (root / relative).resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise TrustAuditError(f'{relative} resolves outside the repository')
    return resolved


def _scan_file(root: Path, relative: str) -> ScanResult:
    """Scan one file, choosing proc-macro mode from the crate that owns it."""
    return scan_tree(root, relative, is_procedural_macro_crate(_manifest_for(root, relative)))


def _manifest_for(root: Path, relative: str) -> Path:
    """Find the nearest ``Cargo.toml`` above a source file."""
    for directory in (root / relative).parents:
        candidate = directory / 'Cargo.toml'
        if candidate.is_file():
            return candidate
        if directory == root:
            break
    return root / 'Cargo.toml'


def _module_targets(root: Path, relative: str,
                    modules: Iterable[ModuleReference]) -> tuple[str, ...]:
    """Resolve every module declaration a file makes to a repository path.

    A ``#[path]`` target is relative to the naming file, as Rust resolves it;
    otherwise the module is searched for beside the file and in its own
    directory. A module that resolves to no file is a structural failure: the
    crate would not compile, and the audit would report a clean scan of code it
    never read.
    """
    targets = []
    for module in modules:
        candidates = (_path_candidates(relative, module) if module.path is not None
                      else _search_candidates(relative, module.name))
        # Containment is checked before existence so an escaping `#[path]` is
        # refused for what it is. Reporting only that the file is absent would
        # invite someone to create it outside the repository and call the audit
        # satisfied.
        if not all(_inside(root, candidate) for candidate in candidates):
            raise TrustAuditError(
                f'{relative}:{module.line}:{module.column} declares module {module.name!r}, '
                f'which resolves outside the repository: {list(candidates)}'
            )
        found = next((candidate for candidate in candidates if (root / candidate).is_file()), None)
        if found is None:
            raise TrustAuditError(
                f'{relative}:{module.line}:{module.column} declares module {module.name!r}, '
                f'which resolves to none of {list(candidates)}'
            )
        targets.append(found)
    return tuple(targets)


def _inside(root: Path, relative: str) -> bool:
    """Report whether a repository-relative path stays beneath ``root``."""
    try:
        resolve_repository_path(root, relative)
    except TrustAuditError:
        return False
    return True


def _path_candidates(relative: str, module: ModuleReference) -> tuple[str, ...]:
    """Return the single path a ``#[path]`` attribute names."""
    return ((PurePosixPath(relative).parent / str(module.path)).as_posix(),)


def _search_candidates(relative: str, name: str) -> tuple[str, ...]:
    """Return the paths Rust searches for a bare ``mod name;``."""
    directory = PurePosixPath(relative).parent.as_posix()
    return tuple(template.format(directory=directory, name=name, suffix=RUST_SUFFIX)
                 for template in MODULE_FILE_CANDIDATES)
