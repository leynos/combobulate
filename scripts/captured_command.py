"""Run one program through cuprum and return its exit status and output.

The proof scripts (`check_kani_corpus.py`, `verus_probe.py`) run installed
verifiers whose exit status alone does not decide anything, so they need the
status and the output together and must not treat a non-zero exit as an error.
This module is that one boundary: each call registers exactly the program it
runs in a local catalogue (`docs/scripting-standards.md`), passes arguments
without a shell, and returns the result for the caller to interpret. A program
that cannot be started raises ``FileNotFoundError`` or ``PermissionError``
instead of returning a status, so a missing verifier is never mistaken for a
failed proof.

Examples
--------
``run_captured(['echo', 'hi'])`` returns ``CapturedResult(0, 'hi\\n')``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from pathlib import Path

from cuprum import ExecutionContext, Program, ProgramCatalogue, ProjectSettings, sh

PROJECT_NAME = "combobulate-proofs"


@dataclasses.dataclass(frozen=True, slots=True)
class CapturedResult:
    """What a finished command reported; e.g. ``CapturedResult(0, 'ok\\n')``.

    ``output`` is standard output followed by standard error, which is the
    order the Kani log parser and the Verus summary reader both expect.
    """

    exit_code: int
    output: str


def run_captured(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> CapturedResult:
    """Run ``argv`` without a shell and return its status and combined output.

    Parameters
    ----------
    argv : Sequence[str]
        The program, by name or absolute path, followed by its arguments.
    cwd : Path | None
        Directory to run in; the caller's directory when omitted.
    env : Mapping[str, str] | None
        Variables overlaid on the live environment for this run only. A value
        cannot unset a variable; run through ``env -u NAME`` for that.

    Returns
    -------
    CapturedResult
        The exit status, returned rather than raised, and the output.

    Raises
    ------
    ValueError
        When ``argv`` is empty.
    FileNotFoundError
        When the program does not exist.
    """
    if not argv:
        raise ValueError("a command needs at least a program")
    program = Program(argv[0])
    catalogue = ProgramCatalogue(
        projects=(
            ProjectSettings(
                name=PROJECT_NAME,
                programs=(program,),
                documentation_locations=("docs/developers-guide.md",),
                noise_rules=(),
            ),
        )
    )
    command = sh.make(program, catalogue=catalogue)(*argv[1:])
    result = command.run_sync(context=ExecutionContext(env=dict(env or {}), cwd=cwd))
    return CapturedResult(result.exit_code, (result.stdout or "") + (result.stderr or ""))
