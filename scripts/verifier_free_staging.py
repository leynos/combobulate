"""Recreate and check the verifier-free staging workspace.

The staging workspace is a fixed path under the repository's ``target``
directory, so a previous run's tree would otherwise survive into the next
build. This module owns that lifecycle: removing any previous tree behind a
narrow guard, and refusing a staged tree that does not match the files the
record binds. Container orchestration stays in ``verifier_free_probe``.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable, Iterator
from pathlib import Path


def _link_components(source: Path, root: Path) -> Iterator[Path]:
    """Yield every symbolic link between ``root`` and ``source``.

    Examples
    --------
    A linked ``.cargo`` directory is reported even when the file is regular::

        list(_link_components(ROOT / '.cargo/config.toml', ROOT))
    """
    relative = source.relative_to(root)
    prefixes = range(1, len(relative.parts) + 1)
    candidates = (
        root.joinpath(*relative.parts[:index]) for index in prefixes
    )
    return filter(Path.is_symlink, candidates)


def verify_source_links(sources: Iterable[Path], root: Path) -> None:
    """Refuse to stage a source reached through a symbolic link.

    ``shutil.copytree`` and ``shutil.copy2`` dereference links by default, so
    a linked source would enter the workspace as a regular file holding
    content from outside the repository. A link can also sit in a directory
    component: if ``.cargo`` is a link, ``.cargo/config.toml`` is not itself a
    link. The staged-tree check cannot see either case, because the link is
    gone by then. Checking every component between the repository root and a
    source before copying keeps the recorded digest tied to repository
    content.

    Parameters
    ----------
    sources
        Repository entries the staging step will copy.
    root
        Repository root that must contain every source without a link.

    Raises
    ------
    ValueError
        If any component between ``root`` and a source is a symbolic link,
        naming each link.

    Examples
    --------
    The fixture root and each file it contributes are both checked::

        verify_source_links([fixture, *staged_sources()], ROOT)
    """
    links = sorted(
        {
            str(link)
            for source in sources
            for link in _link_components(source, root)
        }
    )
    if links:
        raise ValueError(
            f'the staged sources must not be symbolic links: {links}'
        )


def _refuse_symlink(path: Path, description: str) -> None:
    """Refuse a path that is itself a symbolic link.

    Parameters
    ----------
    path
        Path that must be a real entry.
    description
        Role of ``path``, used in the error message.

    Raises
    ------
    ValueError
        If ``path`` is a symbolic link.

    Examples
    --------
    A linked boundary is refused before anything is removed::

        _refuse_symlink(ROOT / 'target', 'staging boundary')
    """
    if path.is_symlink():
        raise ValueError(f'the {description} {path} must not be a symbolic link')


def _refuse_linked_components(directory: Path, boundary: Path) -> None:
    """Refuse a workspace whose path passes through a symbolic link.

    ``resolve`` follows an intermediate link, so removal could reach a
    directory the probe does not own. This check runs before resolution.

    Parameters
    ----------
    directory
        Workspace whose parent components are checked.
    boundary
        Directory that must contain ``directory`` without a link.

    Raises
    ------
    ValueError
        If ``directory`` is not inside ``boundary`` or a component between
        them is a symbolic link, naming each link.

    Examples
    --------
    A linked ``target/staging`` directory is named rather than followed::

        _refuse_linked_components(workspace, ROOT / 'target')
    """
    try:
        intermediates = list(_link_components(directory.parent, boundary))
    except ValueError:
        raise ValueError(
            f'the staging workspace {directory} must be strictly inside {boundary}'
        ) from None
    if intermediates:
        raise ValueError(
            'the staging workspace must not be reached through symbolic links: '
            f'{[str(link) for link in intermediates]}'
        )


def _resolve_owned_workspace(directory: Path, boundary: Path) -> Path:
    """Resolve the workspace and require it to sit strictly inside ``boundary``.

    Resolving first stops a ``..`` component stepping outside. Without this
    check, a linked ``target`` would resolve outside the repository and removal
    could then reach a directory the probe does not own.

    Parameters
    ----------
    directory
        Workspace to resolve.
    boundary
        Directory that must strictly contain the resolved workspace.

    Returns
    -------
    Path
        The resolved workspace.

    Raises
    ------
    ValueError
        If the resolved workspace equals ``boundary`` or lies outside it.

    Examples
    --------
    The workspace under the owned ``target`` directory is accepted::

        _resolve_owned_workspace(ROOT / 'target/workspace', ROOT / 'target')
    """
    owned = boundary.resolve()
    workspace = directory.resolve()
    if workspace == owned or not workspace.is_relative_to(owned):
        raise ValueError(
            f'the staging workspace {workspace} must be strictly inside {owned}'
        )
    return workspace


def _refuse_non_directory(workspace: Path, directory: Path) -> None:
    """Refuse an existing workspace path that is not a directory.

    A regular file where the workspace belongs is not a stale tree, and
    removing it as one would delete a path the probe did not create.

    Parameters
    ----------
    workspace
        Resolved workspace path.
    directory
        Workspace path as the caller named it, used in the error message.

    Raises
    ------
    ValueError
        If ``workspace`` exists and is not a directory.

    Examples
    --------
    A file at the workspace path is refused rather than overwritten::

        _refuse_non_directory(workspace.resolve(), workspace)
    """
    if workspace.exists() and not workspace.is_dir():
        raise ValueError(
            f'the staging workspace {directory} must be a real directory'
        )


def recreate_workspace(directory: Path, boundary: Path) -> None:
    """Remove and recreate the staging workspace inside an owned boundary.

    The workspace path is fixed, so copying into an existing directory would
    let a source deleted from the repository survive in the staged tree. Cargo
    would then build a file the record's digests no longer name, and the
    record would describe different inputs from the ones built. Recreating the
    whole tree makes the staged and recorded sets the same set.

    Removal is deliberately narrow: the guards below refuse a linked boundary,
    workspace, or intermediate directory, and a workspace outside the boundary.

    Parameters
    ----------
    directory
        Workspace to remove and recreate.
    boundary
        Directory that must strictly contain ``directory``.

    Raises
    ------
    ValueError
        If ``boundary``, ``directory``, or a directory between them is a
        symbolic link, if ``directory`` is not a real directory, or if it does
        not resolve to a path strictly inside ``boundary``.

    Examples
    --------
    A rerun starts from an empty workspace::

        recreate_workspace(
            ROOT / 'target/epm1-verifier-free-workspace', ROOT / 'target'
        )
    """
    _refuse_symlink(boundary, 'staging boundary')
    _refuse_symlink(directory, 'staging workspace')
    _refuse_linked_components(directory, boundary)
    workspace = _resolve_owned_workspace(directory, boundary)
    _refuse_non_directory(workspace, directory)
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)


def _staged_entries(workspace: Path) -> list[Path]:
    """Return every staged entry, refusing a linked workspace or entry.

    The root is checked separately because ``rglob`` enumerates a replacement
    link's target without yielding the link. ``is_file`` follows a link, so a
    link at an expected path would otherwise pass the set comparison while the
    digest read content from outside the workspace.

    Parameters
    ----------
    workspace
        Workspace produced by ``_stage_verifier_free_workspace``.

    Returns
    -------
    list[Path]
        Every entry below the workspace, in traversal order.

    Raises
    ------
    RuntimeError
        If the workspace root or any entry is a symbolic link, naming each
        entry.

    Examples
    --------
    A clean staged tree yields its files::

        [path.name for path in _staged_entries(workspace)]
    """
    if workspace.is_symlink():
        raise RuntimeError(
            f"the staged workspace {workspace} must not be a symbolic link"
        )
    entries = list(workspace.rglob("*"))
    links = sorted(str(path) for path in entries if path.is_symlink())
    if links:
        raise RuntimeError(
            "the staged workspace does not match the recorded inputs: "
            f"symbolic links={links}"
        )
    return entries


def _refuse_irregular_entries(entries: Iterable[Path]) -> None:
    """Refuse a staged entry that is neither a directory nor a regular file.

    A special file, such as a named pipe, is neither, so the set comparison
    would pass while the build received an entry the record does not bind.
    Staging cannot create one, so rejecting it keeps the digest bound.

    Parameters
    ----------
    entries
        Entries returned by :func:`_staged_entries`.

    Raises
    ------
    RuntimeError
        If any entry is irregular, naming each one.

    Examples
    --------
    A named pipe at ``probe/fifo`` is named in the refusal::

        _refuse_irregular_entries(_staged_entries(workspace))
    """
    irregular = sorted(
        str(path)
        for path in entries
        if not path.is_dir() and not path.is_file()
    )
    if irregular:
        raise RuntimeError(
            "the staged workspace does not match the recorded inputs: "
            f"irregular entries={irregular}"
        )


def _refuse_file_set_drift(
    entries: Iterable[Path], expected: set[Path]
) -> None:
    """Refuse extra or missing regular files in the staged tree.

    A leftover file is an input the record does not bind; a missing file is a
    digest of nothing. Comparing both directions closes both gaps early.

    Parameters
    ----------
    entries
        Entries returned by :func:`_staged_entries`.
    expected
        The staged copies the record names, plus the generated container file.

    Raises
    ------
    RuntimeError
        If regular files are extra or missing, naming each path.

    Examples
    --------
    A matching tree passes without a return value::

        _refuse_file_set_drift(entries, {*inputs.values(), workspace / 'Containerfile'})
    """
    actual = {path for path in entries if path.is_file()}
    extra = sorted(str(path) for path in actual - expected)
    missing = sorted(str(path) for path in expected - actual)
    if extra + missing:
        raise RuntimeError(
            "the staged workspace does not match the recorded inputs: "
            f"extra={extra}, missing={missing}"
        )


def verify_staged_workspace(
    workspace: Path, inputs: dict[str, Path]
) -> None:
    """Refuse a staged tree that differs from the files the record will bind.

    The record names the inputs it built, so the staged tree must hold exactly
    those regular files plus the generated ``Containerfile``. Links, special
    files, and extra or missing files are refused before the image is built.

    Parameters
    ----------
    workspace
        Workspace produced by ``_stage_verifier_free_workspace``.
    inputs
        Mapping returned by ``staged_inputs``.

    Raises
    ------
    RuntimeError
        If the workspace root or a path it contains is a symbolic link, if a
        path is neither a directory nor a regular file, or if regular files
        are extra or missing, naming each path.

    Examples
    --------
    A matching tree passes without a return value::

        verify_staged_workspace(workspace, staged_inputs(workspace))
    """
    entries = _staged_entries(workspace)
    _refuse_irregular_entries(entries)
    expected = {*inputs.values(), workspace / "Containerfile"}
    _refuse_file_set_drift(entries, expected)