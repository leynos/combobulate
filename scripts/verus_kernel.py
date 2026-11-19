#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = [
#     "cyclopts==5.2.0",
#     "cuprum==0.1.0",
#     "tree-sitter==0.25.2",
#     "tree-sitter-rust==0.24.2",
# ]
# ///
"""Verify the shipped kernel against SC-12, and reject every seeded mutant.

Two Verus roots are run. The positive root includes the production file by
``#[path]`` and must report exactly the pinned ``N verified, 0 errors`` with no
partial-verification suffix. The mutant root states the same clauses for five
deliberately wrong bodies, and each runs alone with ``--verify-root
--verify-function=<name>``.

A sixth, body-tier mutant is produced by copying the production file into a
scratch directory under ``target/`` and replacing the checked addition with a
wrapping one. It must fail a loop invariant, which is what shows the shipped
body's own annotation catches a wrong body rather than only a wrong wrapper.

This module is the pipeline: it builds each helper argv, captures the log and
writes the record. What counts as a verdict is decided in
``verus_kernel_verdicts``, which reads a log and nothing else.

The observations, their digests and the pinned tool identities are committed
under ``tools/verifier-fixtures/verus-kernel/``. They are development
artefacts, not proof-evidence records: admission is PF05.proof@2.3.5's job
(DL-1).

The solver arrives as ``VERUS_Z3_PATH``, which ``make verus-kernel`` exports
and the shared install-prover-tools action sets on the hosted runners. Nothing
here resolves or installs a prover: a missing solver is reported as itself.

For example, ``make verus-kernel`` runs both roots and prints one line per
verdict.
"""

from __future__ import annotations

import json
import shlex
import shutil
import sys
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

sys.path.insert(0, str(Path(__file__).resolve().parent))

from captured_command import run_captured
from kernel_record import (
    ROOT,
    exact_digest,
    is_structural_digest,
    portable_argument,
    portable_log,
    structural_digest,
)
from verus_kernel_identity import identity
from verus_kernel_verdicts import (
    _qualify_body,
    _qualify_mutant,
    _qualify_positive,
)

KERNEL = ROOT / "crates/combobulate-kernel"
POSITIVE_ROOT = KERNEL / "verus/elementwise_add.rs"
MUTANT_ROOT = KERNEL / "verus/elementwise_add_mutants.rs"
CONTRACT = KERNEL / "verus/elementwise_add_contract.rs"
PRODUCTION = KERNEL / "src/elementwise_add.rs"
VERDICTS = ROOT / "scripts/verus_kernel_verdicts.py"
DRIVER = ROOT / "scripts/verus_kernel.py"
IDENTITY = ROOT / "scripts/verus_kernel_identity.py"
RECORD = ROOT / "scripts/kernel_record.py"
OBSERVATIONS = ROOT / "tools/verifier-fixtures/verus-kernel"
KERNEL_WRAP = ROOT / "target/verus-kernel-wrap"

# Variables the verifier must not inherit. Verus sets its own toolchain, and a
# compiler wrapper such as sccache would sit in front of it; Verus refuses to
# start behind one. cuprum overlays variables and cannot unset one, so each
# command runs through `env -u`.
INHERITED_VARIABLES = ("RUSTUP_TOOLCHAIN", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER")

# Each mutant names its own wrapper function and the clause it must violate.
# The clause line is resolved from the file rather than hard-coded, so moving a
# clause keeps the record honest instead of stale.
MUTANTS = {
    "mutant_err": "k2",
    "mutant_late": "k4",
    "mutant_ok_on_overflow": "k1",
    "mutant_mismatch_write": "k5",
    "mutant_early_write": "k5",
}
# M-err must also violate K3: an always-Err body reports a length failure for
# an agreeing shape.
EXTRA_CLAUSES = {"mutant_err": "k3"}
BODY_MUTANT = "wrap"

app = App(help="Verify the shipped elementwise add and reject its seeded mutants.")


@app.default
def main(
    *,
    prover_tools: Annotated[str, Parameter(env_var="PROVER_TOOLS")] = "prover-tools",
    output_dir: Path | None = None,
    verus_installation: Path | None = None,
    z3: Annotated[Path | None, Parameter(env_var="VERUS_Z3_PATH")] = None,
) -> None:
    """Run the positive and mutant roots and print one line per verdict.

    Parameters
    ----------
    prover_tools
        Command prefix that invokes the pinned prover helper.
    output_dir
        Directory receiving the logs; defaults to the committed observations.
    verus_installation
        Installed Verus release; the pin under ``tools/verus/VERSION`` when
        omitted.
    z3
        The Z3 binary; read from ``VERUS_Z3_PATH``, which the shared install
        action sets.
    """
    if z3 is None:
        raise SystemExit("set VERUS_Z3_PATH or pass --z3")
    version = (ROOT / "tools/verus/VERSION").read_text().strip()
    installation = verus_installation or ROOT / ".verus" / version / "verus"
    solver = z3.resolve()
    environment = _verus_environment(solver)
    output = output_dir or OBSERVATIONS
    invocation = _Invocation(prover_tools, installation)
    observations = [_positive(invocation, output, environment)]
    for name, clause in MUTANTS.items():
        observations.append(_mutant(invocation, name, clause, output, environment))
    observations.append(_body_mutant(invocation, output, environment))
    _report(observations)
    if output_dir is None:
        _write_record(version, solver, observations)


def _verus_environment(z3_path: Path) -> dict[str, str]:
    """Return the variables overlaid on every child environment.

    They bind the solver, carry the warnings-as-errors policy through both
    spellings, and name LLVM for any dev-profile backend an opt-in selects.
    """
    return {
        "VERUS_Z3_PATH": str(z3_path),
        "RUSTFLAGS": "-D warnings",
        "CARGO_ENCODED_RUSTFLAGS": "-D\x1fwarnings",
        "CARGO_PROFILE_DEV_CODEGEN_BACKEND": "llvm",
    }


def _without_inherited_variables(argv: list[str]) -> list[str]:
    """Return ``argv`` run through ``env -u`` for every inherited variable."""
    unset = [flag for name in INHERITED_VARIABLES for flag in ("-u", name)]
    return ["env", *unset, *argv]


def _capture(
    argv: list[str], cwd: Path, output: Path, environment: dict[str, str]
) -> dict:
    """Capture one run, with the committed log stripped of host-bound noise.

    Verus prints absolute source paths in its diagnostics, and the shared
    helper prints an install line whenever it has just built its environment.
    Committing either would bind the record to one worktree and one cache
    state, so both are removed from the copy that is written. The execution is
    unaffected: only the copy that is read back and committed is rewritten.

    Raises
    ------
    OSError
        When the log cannot be written after capture.
    """
    result = run_captured(
        _without_inherited_variables(argv), cwd=cwd, env=environment
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(portable_log(result.output), encoding="utf-8")
    print(f"{output.name}: exit {result.exit_code}", flush=True)
    # The digest must bind the committed bytes, not the pre-sanitisation ones,
    # or a reader checking the record against the file would see a mismatch.
    return {
        "command": [portable_argument(argument) for argument in argv],
        "cwd": str(cwd.relative_to(ROOT)),
        "exit_code": result.exit_code,
        "log": str(output.relative_to(ROOT)),
        "sha256": exact_digest(output),
    }


class _Invocation:
    """One pinned-helper invocation, holding the two settings every run shares.

    Running through ``prover-tools verus run`` rather than the Verus binary
    directly is what makes the Make target's contract meaningful: the argument
    vector the helper receives is the one a real run uses.
    """

    def __init__(self, prover_tools: str, installation: Path) -> None:
        """Split the pinned helper command and remember the Verus binary.

        The pin arrives as one shell-quoted string, so it is split rather than
        passed whole: the helper has to see its own arguments separately, as
        ``uv tool run --from … prover-tools`` does.
        """
        self._prefix = shlex.split(prover_tools)
        self._installation = installation

    def command(self, proof_file: Path, *selection: str) -> list[str]:
        """Return the helper argv for one proof root and its function selection."""
        return [
            *self._prefix,
            "verus", "run",
            "--repo-root", str(ROOT),
            "--proof-file", str(proof_file),
            "--verus-bin", str(self._installation),
            "--extra-arg=--crate-type=lib",
            "--extra-arg=--edition=2024",
            *selection,
        ]


def _positive(invocation: _Invocation, output: Path, environment: dict[str, str]) -> dict:
    """Run the positive root and qualify its exact verified count."""
    log = output / "positive.log"
    record = _capture(invocation.command(POSITIVE_ROOT), ROOT, log, environment)
    record["candidate"] = "positive"
    record["verdict"] = _qualify_positive(log.read_text(), record["exit_code"])
    return record


def _mutant(
    invocation: _Invocation,
    name: str,
    clause: str,
    output: Path,
    environment: dict[str, str],
) -> dict:
    """Run one seeded mutant and qualify its rejection."""
    argv = invocation.command(
        MUTANT_ROOT, "--extra-arg=--verify-root", f"--extra-arg=--verify-function={name}"
    )
    log = output / f"{name}.log"
    record = _capture(argv, ROOT, log, environment)
    record["candidate"] = name
    clauses = [clause, *([EXTRA_CLAUSES[name]] if name in EXTRA_CLAUSES else [])]
    record["verdict"] = _qualify_mutant(
        log.read_text(), record["exit_code"], name, clauses, MUTANT_ROOT
    )
    return record


def _body_mutant(invocation: _Invocation, output: Path, environment: dict[str, str]) -> dict:
    """Verify a wrapping copy of the shipped body and require a loop failure.

    The copy lives under ``target/`` so it is never built by an ordinary Cargo
    invocation, and it is recreated on every run.
    """
    scratch = KERNEL_WRAP
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True)
    shipped = PRODUCTION.read_text(encoding="utf-8")
    mutated = shipped.replace(
        "lhs[scan].checked_add(rhs[scan]).is_none()",
        "lhs[scan].checked_add(rhs[scan]).is_some() && false",
    )
    if mutated == shipped:
        raise RuntimeError(
            "the body mutation no longer matches the shipped source; it replaces "
            "`lhs[scan].checked_add(rhs[scan]).is_none()`, so renaming the pass-1 "
            "counter breaks it rather than silently producing an unmutated copy"
        )
    (scratch / "elementwise_add.rs").write_text(mutated, encoding="utf-8")
    (scratch / "contract.rs").write_text(CONTRACT.read_text(encoding="utf-8"), encoding="utf-8")
    (scratch / "wrap.rs").write_text(_WRAP_ROOT, encoding="utf-8")
    log = output / "wrap.log"
    record = _capture(
        invocation.command(scratch / "wrap.rs"), ROOT, log, environment
    )
    record["candidate"] = BODY_MUTANT
    record["verdict"] = _qualify_body(log.read_text(), record["exit_code"])
    return record


_WRAP_ROOT = """//! Generated root for the body-tier wrapping mutant.
#![no_std]
#![feature(proc_macro_hygiene)]
#![allow(dead_code)]
use vstd::prelude::*;

#[path = "contract.rs"]
mod contract;
#[path = "elementwise_add.rs"]
mod elementwise_add;

verus! {
pub fn wrap(lhs: &[i64], rhs: &[i64], out: &mut [i64]) -> (r: Result<(), elementwise_add::AddFailure>) {
    elementwise_add::add_i64_into(lhs, rhs, out)
}
}
"""


def _report(observations: list[dict]) -> None:
    """Print one acceptance line per observation.

    Raises
    ------
    RuntimeError
        When any observation lacks a verdict; a run that produced a log but no
        verdict is not evidence of anything.
    """
    for record in observations:
        verdict = record.get("verdict")
        if verdict is None:
            raise RuntimeError(f"{record['candidate']}: no verdict was reached")
        if verdict["kind"] == "positive":
            print(f"positive: verification results:: {verdict['verified']} verified, 0 errors")
        elif verdict["kind"] == "mutant":
            lines = ", ".join(f"{clause} (elementwise_add_mutants.rs:{line})"
                              for line, clause in sorted(verdict["lines"].items()))
            print(f"mutant {record['candidate']}: rejected at {lines}")
        else:
            print(f"body mutant {BODY_MUTANT}: rejected at loop invariant")


def _write_record(version: str, z3_path: Path, observations: list[dict]) -> None:
    """Write the observations, their digests and the tool identities.

    The record is a development artefact, not an evidence record: DL-1 hands
    admission to PF05.proof@2.3.5, which re-runs rather than admitting these
    logs.

    Every script that produced the record is bound alongside the kernel
    sources, so a reader can tell which code decided these observations.
    Splitting one script into several would otherwise leave a deciding rule or
    the identity statement outside the record.
    """
    OBSERVATIONS.mkdir(parents=True, exist_ok=True)
    sources = [
        CONTRACT,
        PRODUCTION,
        POSITIVE_ROOT,
        MUTANT_ROOT,
        DRIVER,
        VERDICTS,
        IDENTITY,
        RECORD,
    ]
    digests = {
        str(source.relative_to(ROOT)): structural_digest(source) for source in sources
    }
    if not all(is_structural_digest(value) for value in digests.values()):
        raise RuntimeError("every bound source must carry a structural digest")
    (OBSERVATIONS / "provenance.json").write_text(
        json.dumps(
            {
                "verus": version,
                "z3": portable_argument(str(z3_path)),
                "z3_sha256": exact_digest(z3_path),
                "admission": "PF05.proof@2.3.5 re-runs these; they are not admitted evidence",
                # DL-14: the tuple says which operation these observations are
                # about, so a later release cannot read them as evidence for a
                # different body.
                "identity": identity(
                    structural_digest(PRODUCTION),
                    structural_digest(CONTRACT),
                ),
                "source_digests": digests,
                "observations": observations,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    app()
