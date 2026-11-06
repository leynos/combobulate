#!/usr/bin/env python3
"""Prepare and run the cardinality compile-fail gate before any test body runs.

The gate lives in its own Cargo workspace. Preparation builds its test binary
with ``--no-run`` and records the executable Cargo reports, so the root test
runs the binary from the build that just completed rather than searching a
directory for the newest file. Selection reads Cargo's ``compiler-artifact``
JSON, which names the exact output path even when an inherited
``CARGO_TARGET_DIR`` redirects the build.

The same recipe runs the recorded binary under ``timeout``, so the direct
``make test-ui`` route is bounded on the same terms as the root test: a child
that ignores ``SIGTERM`` is killed after the grace period, and a kill this
recipe did not announce is not reported as a deadline overrun. Because the
child runs in its own process group so that the signal reaches its descendants,
``timeout`` mirrors the ending signal by killing itself: an escalated run has no
exit status at all, and only the ``-9`` return code of ``subprocess`` reports
it. The status this module returns is normalised to the shell's ``128 + N``
convention so a Make recipe sees the familiar number.

For example::

    python3 scripts/cardinality_ui_gate.py prepare
    python3 scripts/cardinality_ui_gate.py run

Preparation prints the recorded path; ``run`` executes it and propagates its
status.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'tools/gates/cardinality-ui/Cargo.toml'
GATE_DIRECTORY = MANIFEST.parent
RECORD = GATE_DIRECTORY / 'target/cardinality-ui-binary'
EXECUTABLE_NAME = 'cardinality_ui'

# The recorded run has no nextest behind it, so it carries the same
# 600-second bound the nextest override applies to the root test.
DEADLINE_SECONDS = '600'

# The escalation grace and the announcement that distinguishes an enforced
# kill from a child that died of `SIGKILL` for any other reason.
KILL_GRACE = '2s'
TIMEOUT_EXIT = 124
KILL_SIGNAL = -9
KILL_MARKER = 'sending signal KILL to command'

# Shell convention: a signal death is reported as 128 + the signal number.
SIGNAL_EXIT_BASE = 128

# Environment a gate child must not inherit: `trybuild` reads this variable to
# decide which package's manifest to copy, and Cargo sets it to the root
# package for every test process.
MANIFEST_DIR_VARIABLE = 'CARGO_MANIFEST_DIR'

# Build-tool variables that would redirect this build away from the route the
# root test expects; the recorded path makes the two agree either way, so they
# are removed only so a preparation and its run cannot disagree.
REDIRECTING_VARIABLES = (
    'CARGO_TARGET_DIR',
    'CARGO_BUILD_TARGET',
    'CARGO_PROFILE_DEV_CODEGEN_BACKEND',
)


def _cargo() -> str:
    """Return the Cargo executable the surrounding route selected."""
    return os.environ.get('CARGO', 'cargo')


def _base_environment() -> dict[str, str]:
    """Return the environment shared by preparation and execution.

    ``RUSTFLAGS`` is composed here because the Make recipes assign it, and an
    assignment replaces every configuration source rather than merging with
    it. Clippy is not involved; the gate is a test build, so the development
    flags are what it needs.
    """
    environment = dict(os.environ)
    standard = os.environ.get('DEV_RUST_FLAGS', '')
    inherited = os.environ.get('RUSTFLAGS', '')
    environment['RUSTFLAGS'] = f'{inherited} {standard}'.strip()
    return environment


def _build_arguments() -> list[str]:
    """Return the exact Cargo arguments preparation uses."""
    return [
        'test',
        '--no-run',
        '--message-format=json',
        '--manifest-path',
        str(MANIFEST),
        '--test',
        EXECUTABLE_NAME,
    ]


def _artifact_executable(stream: str) -> str | None:
    """Return the first executable path in Cargo's JSON message stream.

    Cargo emits one JSON object per line. Only ``compiler-artifact`` messages
    that name this test target carry an executable, and a line that is not
    valid JSON is skipped: Cargo also writes human-readable progress to the
    same stream, and a garbled line must not abort selection.
    """
    for line in stream.splitlines():
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get('reason') != 'compiler-artifact':
            continue
        if message.get('target', {}).get('name') != EXECUTABLE_NAME:
            continue
        executable = message.get('executable')
        if executable:
            return executable
    return None


def prepare() -> Path:
    """Build the gate's test binary and record the executable Cargo reports.

    The previous record is withdrawn before the build starts, so a preparation
    that fails leaves nothing runnable behind. Keeping the old path would let a
    later ``run`` execute a binary from a build that no longer describes the
    tree, and a failure observed through Make cannot be relied on to stop every
    later invocation.

    Returns
    -------
    Path
        The absolute path of the test binary that was just built.

    Raises
    ------
    RuntimeError
        When Cargo fails, or when its output names no executable for the gate
        test target. Neither case leaves a usable record.
    """
    _withdraw_record()
    environment = _base_environment()
    for variable in REDIRECTING_VARIABLES:
        environment.pop(variable, None)
    result = subprocess.run(
        [_cargo(), *_build_arguments()],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(
            'the cardinality gate test binary could not be built with '
            '`make prepare-dependencies` and `make prepare-ui-gate`'
        )
    executable = _artifact_executable(result.stdout)
    if executable is None:
        raise RuntimeError(
            'Cargo reported no executable for the cardinality gate test target; '
            'the build record cannot name a binary to run'
        )
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(f'{executable}\n')
    return Path(executable)


def _withdraw_record() -> None:
    """Remove any record left by an earlier preparation.

    A missing record is the normal cold-checkout state, so this is not an
    error. Any other removal failure is reported: continuing would leave a
    stale path available to a later ``run``.
    """
    try:
        RECORD.unlink()
    except FileNotFoundError:
        return
    except OSError as error:
        raise RuntimeError(
            f'the previous cardinality gate build record could not be removed: '
            f'{RECORD}: {error}'
        ) from error


def recorded_binary() -> Path:
    """Return the executable recorded by the last successful preparation.

    Raises
    ------
    RuntimeError
        When no record exists or it is empty, which is what a cold checkout or
        an interrupted preparation produces.
    """
    try:
        text = RECORD.read_text()
    except OSError as error:
        raise RuntimeError(
            f'the cardinality gate build record is unreadable: {RECORD}'
        ) from error
    path = text.strip()
    if not path:
        raise RuntimeError(f'the cardinality gate build record is empty: {RECORD}')
    return Path(path)


def run() -> int:
    """Run the recorded gate binary under a bounded, observed deadline.

    Returns
    -------
    int
        The child's exit status, or a failure status when the deadline ended
        the run. A kill this recipe did not announce is not classified as a
        deadline, so its status is propagated unchanged for the operator to
        read.

    Raises
    ------
    RuntimeError
        When no prepared binary exists.
    """
    binary = recorded_binary()
    if not binary.is_file():
        raise RuntimeError(
            f'the recorded cardinality gate binary no longer exists: {binary}; '
            'run `make prepare-ui-gate` again'
        )
    environment = _base_environment()
    environment.pop(MANIFEST_DIR_VARIABLE, None)
    result = subprocess.run(
        _run_command(binary),
        cwd=GATE_DIRECTORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    announcement = _deadline_announcement(result.returncode, result.stderr)
    if announcement is not None:
        print(announcement, file=sys.stderr)
    return _exit_status(result.returncode)


def _exit_status(returncode: int) -> int:
    """Convert a ``subprocess`` return code into a process exit status.

    ``subprocess`` reports a child ended by a signal as ``-N``; a shell reports
    the same outcome as ``128 + N``. Only the second form is meaningful as the
    exit status of this process, so the conversion keeps the status that Make
    prints equal to the one an operator would see from any shell wrapper.
    """
    return SIGNAL_EXIT_BASE - returncode if returncode < 0 else returncode


def _run_command(binary: Path) -> list[str]:
    """Return the bounded invocation that runs one prepared gate binary.

    The recorded run has no nextest behind it, so it carries the same explicit
    deadline the root test does. ``--verbose`` makes ``timeout`` announce each
    signal it sends, which is what makes escalation observable rather than
    inferred from a status other processes also produce.
    """
    return [
        'timeout',
        '--verbose',
        '--signal=TERM',
        f'--kill-after={KILL_GRACE}',
        DEADLINE_SECONDS,
        str(binary),
    ]


def _deadline_announcement(status: int, stderr: str) -> str | None:
    """Describe a deadline this recipe enforced, or return ``None``.

    A child can end of ``SIGKILL`` because this recipe killed it after it
    ignored ``SIGTERM``, or because something else killed it. Both leave the
    wrapper with no exit status and the same signal. Only the announcement
    ``timeout`` writes in verbose mode separates them, so an unannounced kill is
    left to the operator's diagnostics rather than being reported as a deadline
    this recipe did not enforce.
    """
    if status == TIMEOUT_EXIT:
        return (
            f'the cardinality gate exceeded its {DEADLINE_SECONDS}s deadline '
            'and was terminated'
        )
    if status == KILL_SIGNAL and KILL_MARKER in stderr:
        return (
            'the cardinality gate ignored SIGTERM and was killed after '
            f'{KILL_GRACE}'
        )
    return None


def main(arguments: list[str]) -> int:
    """Dispatch one preparation or execution request.

    Parameters
    ----------
    arguments
        One of ``prepare`` or ``run``.

    Returns
    -------
    int
        A process exit status.
    """
    if arguments == ['prepare']:
        print(prepare())
        return 0
    if arguments == ['run']:
        try:
            return run()
        except RuntimeError as error:
            print(error, file=sys.stderr)
            return 1
    print('usage: cardinality_ui_gate.py prepare|run', file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
