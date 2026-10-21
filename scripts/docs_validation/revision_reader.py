"""Read committed governance registers through the Git command-line adapter."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _git_output(root: Path, arguments: list[str], failure: str) -> bytes:
    """Run one read-only Git command for this adapter and attach its failure context."""
    try:
        result = subprocess.run(['git', *arguments], cwd=root, capture_output=True, check=False)
    except OSError as error:
        raise AssertionError(f'Cannot run Git while {failure}: {error}') from error
    if result.returncode != 0:
        detail = result.stderr.decode(errors='replace').strip()
        raise AssertionError(f'{failure}: {detail}')
    return result.stdout


def git_head_revision(root: Path) -> str:
    """Return the checked-out commit used to bind current-run checker results."""
    output = _git_output(
        root, ['rev-parse', '--verify', '--end-of-options', 'HEAD^{commit}'],
        'Cannot resolve the current source revision',
    )
    return output.decode('ascii').strip()


def git_bytes_at_revision(root: Path, revision: str, path: str) -> bytes | None:
    """Read a committed file; return None only when its path is absent.

    Bind the repository root once before injecting the adapter into
    a check::

        reader = partial(git_bytes_at_revision, repository_root)
        source = reader(base_revision, 'docs/adrs/adr-0002-governance.md')

    A present path returns its raw bytes. A missing path returns ``None``; a
    revision or command failure raises ``AssertionError``.
    """
    resolved = _git_output(
        root, ['rev-parse', '--verify', '--end-of-options', f'{revision}^{{commit}}'],
        f'Cannot resolve base revision {revision}',
    )
    base_commit = resolved.decode('ascii').strip()
    entry = _git_output(
        root, ['ls-tree', '-z', base_commit, '--', path],
        f'Cannot inspect {path} at base revision {revision}',
    )
    if not entry:
        return None
    return _git_output(
        root, ['show', f'{base_commit}:{path}'],
        f'Cannot read {path} at base revision {revision}',
    )


def git_json_at_revision(root: Path, revision: str, path: str) -> dict | None:
    """Read JSON from Git; return None only when the path is absent at the revision.

    A present register returns its parsed JSON value; revision and command
    failures raise ``AssertionError``, while malformed JSON raises
    ``json.JSONDecodeError``.
    """
    record = git_bytes_at_revision(root, revision, path)
    return json.loads(record) if record is not None else None


def working_tree_bytes(root: Path, path: str) -> bytes | None:
    """Read a current file, returning None when the path is absent.

    Callers validate repository-relative paths before using this adapter.
    """
    try:
        return (root / path).read_bytes()
    except FileNotFoundError:
        return None
