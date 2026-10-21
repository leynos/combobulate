"""Run fixture Git commands against one owned repository.

Tests that create a throwaway repository pass ``cwd`` and expect Git to use
it. A Git hook, an IDE task, or a wrapper can export repository-location
variables such as ``GIT_DIR`` that take precedence over the current directory,
which would aim the fixture's ``init``, ``add``, and ``commit`` at the
caller's repository instead. ``fixture_environment`` removes those variables
so the fixture only ever acts on the directory it names.
"""
from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

REPOSITORY_LOCATION_VARIABLES = (
    'GIT_ALTERNATE_OBJECT_DIRECTORIES',
    'GIT_CEILING_DIRECTORIES',
    'GIT_COMMON_DIR',
    'GIT_DIR',
    'GIT_DISCOVERY_ACROSS_FILESYSTEM',
    'GIT_INDEX_FILE',
    'GIT_NAMESPACE',
    'GIT_OBJECT_DIRECTORY',
    'GIT_PREFIX',
    'GIT_WORK_TREE',
)


def fixture_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return the inherited environment without repository-location variables.

    For example, a hook-exported ``GIT_DIR`` does not reach the fixture::

        >>> clean = fixture_environment({'GIT_DIR': '/elsewhere', 'HOME': '/home/ex'})
        >>> sorted(clean)
        ['HOME']
    """
    environment = dict(os.environ if base is None else base)
    for name in REPOSITORY_LOCATION_VARIABLES:
        environment.pop(name, None)
    return environment


FIXTURE_IDENTITY = (
    '-c', 'user.name=Fixture',
    '-c', 'user.email=fixture@example.org',
    '-c', 'commit.gpgsign=false',
)


def run_git(repository: Path, *arguments: str) -> str:
    """Run one fixture Git command in ``repository`` and return its stripped standard output.

    Fixture identity and signing are supplied per call so no global or
    repository configuration decides whether the fixture can commit::

        run_git(root, 'init', '--quiet')
    """
    result = subprocess.run(
        ['git', *FIXTURE_IDENTITY, *arguments],
        cwd=repository,
        env=fixture_environment(),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
