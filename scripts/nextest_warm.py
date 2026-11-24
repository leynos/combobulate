#!/usr/bin/env python3
"""Warm the nested builds that root tests would otherwise compile in a timed body.

Nextest setup scripts (``.config/nextest.toml``) run this before the tests that
start a nested Cargo build, so the build's cost is paid once, under an allowance
of its own, rather than inside a test's termination budget. A cold ``target``
directory, or a host whose compile pool is queueing, then fails no sound
assertion with a timeout.

Each subcommand repeats exactly what one family of tests does, with the same
scrubbed environment and the same target directory, so the test finds the work
done. The warm-up never judges a result: a fixture that is meant to fail to
build, or a gate that fails, is reported by its own test with its own output.
Only a missing prerequisite or a timeout stops the run.

For example::

    python3 scripts/nextest_warm.py fixtures
    python3 scripts/nextest_warm.py gate
    python3 scripts/nextest_warm.py workspace
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import cardinality_ui_gate

ROOT = cardinality_ui_gate.ROOT

# Build selectors a fixture must not inherit: an inherited value would make the
# fixture depend on how the suite was invoked. The fixture tests remove the same
# three names, which is what keeps this warm-up and those tests on one build.
FIXTURE_SCRUBBED_VARIABLES = (
    'RUSTFLAGS',
    'CARGO_ENCODED_RUSTFLAGS',
    'CARGO_BUILD_TARGET',
)

# Fixture manifests and the directory (under `<target>/tmp`) each test builds
# into, which the tests name through `CARGO_TARGET_TMPDIR`.
FIXTURE_BUILDS = (
    ('tools/fixtures/polars-surface-absent/Cargo.toml', 'polars-surface-absent'),
    ('tools/fixtures/native-consumer/Cargo.toml', 'native-consumer'),
)


def _cargo() -> str:
    """Return the Cargo executable the surrounding route selected."""
    return os.environ.get('CARGO', 'cargo')


def target_tmpdir() -> Path:
    """Return the directory Cargo names ``CARGO_TARGET_TMPDIR`` for root tests.

    It is ``tmp`` under the workspace's resolved target directory, so asking
    Cargo for that directory keeps this warm-up on the path the tests compute
    even when ``CARGO_TARGET_DIR`` redirects the build (as coverage runs do).

    Raises
    ------
    RuntimeError
        When Cargo cannot report the workspace metadata.
    """
    result = subprocess.run(
        [
            _cargo(),
            '--frozen',
            'metadata',
            '--no-deps',
            '--format-version',
            '1',
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f'cargo metadata failed:\n{result.stderr}')
    return Path(json.loads(result.stdout)['target_directory']) / 'tmp'


def fixture_environment(target_dir: Path) -> dict[str, str]:
    """Return the environment a fixture build runs in.

    Parameters
    ----------
    target_dir
        The fixture's private target directory.
    """
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in FIXTURE_SCRUBBED_VARIABLES
    }
    environment['CARGO_TARGET_DIR'] = str(target_dir)
    return environment


def warm_fixtures() -> None:
    """Build both consumer fixtures the root tests build.

    The absence fixture is meant to fail, and its test asserts that; the
    dependencies it shares with the consumer fixture are what this builds.
    """
    tmpdir = target_tmpdir()
    for manifest, directory in FIXTURE_BUILDS:
        completed = subprocess.run(
            [
                _cargo(),
                '--frozen',
                'build',
                '--locked',
                '--offline',
                '--message-format=short',
                '--manifest-path',
                str(ROOT / manifest),
            ],
            cwd=ROOT,
            env=fixture_environment(tmpdir / directory),
            check=False,
        )
        print(
            f'nextest-warm: {directory} build finished with status '
            f'{completed.returncode} (its own test judges the result)',
            file=sys.stderr,
        )


def gate_environment() -> dict[str, str]:
    """Return the environment the root test gives the cardinality gate."""
    return {
        name: value
        for name, value in os.environ.items()
        if name != cardinality_ui_gate.MANIFEST_DIR_VARIABLE
    }


def warm_gate() -> None:
    """Run the recorded gate binary the way the root test runs it.

    The gate's `trybuild` cases compile generated crates when the binary runs,
    which is the cost the root test would otherwise pay under its deadline. The
    binary's build is `make prepare-ui-gate`'s; this is its first run.

    Raises
    ------
    RuntimeError
        When preparation has not recorded a binary.
    """
    binary = cardinality_ui_gate.recorded_binary()
    completed = subprocess.run(
        [str(binary)],
        cwd=cardinality_ui_gate.GATE_DIRECTORY,
        env=gate_environment(),
        check=False,
    )
    print(
        f'nextest-warm: gate run finished with status {completed.returncode} '
        '(its own test judges the result)',
        file=sys.stderr,
    )


def warm_workspace() -> None:
    """Resolve the workspace's whole graph once, offline.

    The read-only workspace tests run ``cargo tree`` and ``cargo metadata``;
    neither compiles anything, but the first one pays for loading the registry
    index and resolving the lockfile, so this does that outside any test.
    """
    subprocess.run(
        [
            _cargo(),
            '--frozen',
            'tree',
            '--prefix',
            'none',
            '--workspace',
            '--target',
            'all',
            '--edges',
            'all',
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        check=False,
    )


COMMANDS = {
    'fixtures': warm_fixtures,
    'gate': warm_gate,
    'workspace': warm_workspace,
}


def main(arguments: list[str]) -> int:
    """Run the named warm-up and return the process status.

    Parameters
    ----------
    arguments
        The command line after the program name: one of ``COMMANDS``.
    """
    if len(arguments) != 1 or arguments[0] not in COMMANDS:
        print(f'usage: nextest_warm.py {{{"|".join(COMMANDS)}}}', file=sys.stderr)
        return 2
    try:
        COMMANDS[arguments[0]]()
    except RuntimeError as error:
        print(f'nextest-warm: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
