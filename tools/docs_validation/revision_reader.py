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


def git_json_at_revision(root: Path, revision: str, path: str) -> dict | None:
    """Read JSON from Git; return None only when the path is absent at the revision.

    Bind the repository root once before injecting the adapter into
    ``check_frozen``::

        reader = partial(git_json_at_revision, repository_root)
        register = reader(base_revision, 'spec/decisions.json')

    A present register returns its parsed JSON value. A missing register returns
    ``None``; a revision or command failure raises ``AssertionError``, while
    malformed JSON raises ``json.JSONDecodeError``.
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
    record = _git_output(
        root, ['show', f'{base_commit}:{path}'],
        f'Cannot read {path} at base revision {revision}',
    )
    return json.loads(record)
