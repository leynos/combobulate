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
    for index in range(1, len(relative.parts) + 1):
        candidate = root.joinpath(*relative.parts[:index])
        if candidate.is_symlink():
            yield candidate


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


def recreate_workspace(directory: Path, boundary: Path) -> None:
    """Remove and recreate the staging workspace inside an owned boundary.

    The workspace path is fixed, so copying into an existing directory would
    let a source deleted from the repository survive in the staged tree. Cargo
    would then build a file the record's digests no longer name, and the
    record would describe different inputs from the ones built. Recreating the
    whole tree makes the staged and recorded sets the same set.

    Removal is deliberately narrow. A boundary or workspace that is a
    symbolic link is refused rather than followed, and every directory between
    the boundary and the workspace is checked for links, because ``resolve``
    would otherwise follow an intermediate link to a directory the probe does
    not own. The workspace is resolved before containment, so a ``..``
    component cannot step outside. The resolved workspace must sit strictly
    inside ``boundary``. Without the boundary check, a linked ``target`` would
    resolve outside the repository and its containment would be measured
    against the link target, so removal could reach a directory the probe does
    not own.

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
    if boundary.is_symlink():
        raise ValueError(
            f'the staging boundary {boundary} must not be a symbolic link'
        )
    if directory.is_symlink():
        raise ValueError(
            f'the staging workspace {directory} must not be a symbolic link'
        )
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
    owned = boundary.resolve()
    workspace = directory.resolve()
    if workspace == owned or not workspace.is_relative_to(owned):
        raise ValueError(
            f'the staging workspace {workspace} must be strictly inside {owned}'
        )
    if workspace.exists() and not workspace.is_dir():
        raise ValueError(
            f'the staging workspace {directory} must be a real directory'
        )
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)


def verify_staged_workspace(
    workspace: Path, inputs: dict[str, Path]
) -> None:
    """Refuse a staged tree that differs from the files the record will bind.

    The record names the inputs it built, so the staged tree must hold exactly
    those regular files plus the generated ``Containerfile``. A leftover file
    is an input the record does not bind; a missing file is a digest of
    nothing. Comparing both directions closes either gap before the image is
    prepared.

    Symbolic links are refused outright. ``is_file`` follows a link to a
    regular target, so a link at an expected path would pass the set
    comparison while the digest read content from outside the workspace.
    The workspace root is checked separately because ``rglob`` enumerates a
    replacement link's target without yielding the link itself. Staging
    dereferences links, so one can only appear through local tampering;
    rejecting it keeps the recorded digest bound to the workspace.

    Parameters
    ----------
    workspace
        Workspace produced by ``_stage_verifier_free_workspace``.
    inputs
        Mapping returned by ``staged_inputs``.

    Raises
    ------
    RuntimeError
        If the workspace root or a path it contains is a symbolic link, or if
        regular files are extra or missing, naming each path.

    Examples
    --------
    A matching tree passes without a return value::

        verify_staged_workspace(workspace, staged_inputs(workspace))
    """
    if workspace.is_symlink():
        raise RuntimeError(
            f"the staged workspace {workspace} must not be a symbolic link"
        )
    expected = {*inputs.values(), workspace / "Containerfile"}
    entries = list(workspace.rglob("*"))
    links = sorted(str(path) for path in entries if path.is_symlink())
    if links:
        raise RuntimeError(
            "the staged workspace does not match the recorded inputs: "
            f"symbolic links={links}"
        )
    actual = {path for path in entries if path.is_file()}
    extra = sorted(str(path) for path in actual - expected)
    missing = sorted(str(path) for path in expected - actual)
    if extra or missing:
        raise RuntimeError(
            "the staged workspace does not match the recorded inputs: "
            f"extra={extra}, missing={missing}"
        )