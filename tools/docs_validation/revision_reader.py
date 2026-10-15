"""Read committed governance registers through the Git command-line adapter."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


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
    try:
        result = subprocess.run(['git', 'show', f'{revision}:{path}'], cwd=root, capture_output=True,
                                text=True, check=False)
    except OSError as error:
        message = f'Cannot run Git while reading {path} at base revision {revision}: {error}'
        raise AssertionError(message) from error
    if result.returncode != 0:
        path_is_missing = (
            'does not exist' in result.stderr or 'exists on disk, but not in' in result.stderr
        )
        if path_is_missing:
            return None
        message = f'Cannot read {path} at base revision {revision}: {result.stderr.strip()}'
        raise AssertionError(message)
    return json.loads(result.stdout)
