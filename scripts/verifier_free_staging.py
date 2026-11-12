"""Recreate and check the verifier-free staging workspace.

The staging workspace is a fixed path under the repository's ``target``
directory, so a previous run's tree would otherwise survive into the next
build. This module owns that lifecycle: removing any previous tree behind a
narrow guard, and refusing a staged tree that does not match the files the
record binds. Container orchestration stays in ``verifier_free_probe``.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def recreate_workspace(directory: Path, boundary: Path) -> None:
    """Remove and recreate the staging workspace inside an owned boundary.

    The workspace path is fixed, so copying into an existing directory would
    let a source deleted from the repository survive in the staged tree. Cargo
    would then build a file the record's digests no longer name, and the
    record would describe different inputs from the ones built. Recreating the
    whole tree makes the staged and recorded sets the same set.

    Removal is deliberately narrow. A workspace that is a symbolic link is
    refused rather than followed, and the resolved workspace must sit strictly
    inside ``boundary``; that keeps a mistaken path or a planted link from
    deleting a directory the probe does not own.

    Parameters
    ----------
    directory
        Workspace to remove and recreate.
    boundary
        Directory that must strictly contain ``directory``.

    Raises
    ------
    ValueError
        If ``directory`` is a symbolic link, is not a real directory, or does
        not resolve to a path strictly inside ``boundary``.

    Examples
    --------
    A rerun starts from an empty workspace::

        recreate_workspace(
            ROOT / 'target/epm1-verifier-free-workspace', ROOT / 'target'
        )
    """
    owned = boundary.resolve()
    if directory.is_symlink():
        raise ValueError(
            f'the staging workspace {directory} must not be a symbolic link'
        )
    workspace = directory.parent.resolve() / directory.name
    if workspace == owned or not workspace.is_relative_to(owned):
        raise ValueError(
            f'the staging workspace {workspace} must be strictly inside {owned}'
        )
    if directory.exists() and not directory.is_dir():
        raise ValueError(
            f'the staging workspace {directory} must be a real directory'
        )
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)


def verify_staged_workspace(
    workspace: Path, inputs: dict[str, Path]
) -> None:
    """Refuse a staged tree that differs from the files the record will bind.

    The record names the inputs it built, so the staged tree must hold exactly
    those regular files plus the generated ``Containerfile``. A leftover file
    is an input the record does not bind; a missing file is a digest of
    nothing. Comparing both directions closes either gap before the image is
    prepared.

    Parameters
    ----------
    workspace
        Workspace produced by ``_stage_verifier_free_workspace``.
    inputs
        Mapping returned by ``staged_inputs``.

    Raises
    ------
    RuntimeError
        If the workspace holds extra or missing regular files, naming each
        path.

    Examples
    --------
    A matching tree passes without a return value::

        verify_staged_workspace(workspace, staged_inputs(workspace))
    """
    expected = {*inputs.values(), workspace / "Containerfile"}
    actual = {path for path in workspace.rglob("*") if path.is_file()}
    extra = sorted(str(path) for path in actual - expected)
    missing = sorted(str(path) for path in expected - actual)
    if extra or missing:
        raise RuntimeError(
            "the staged workspace does not match the recorded inputs: "
            f"extra={extra}, missing={missing}"
        )