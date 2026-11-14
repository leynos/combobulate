#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["cyclopts==5.2.0", "cuprum==0.1.0"]
# ///
"""Run and qualify the pinned Verus wiring candidates.

The four candidates (macro, attributes, companion and single-root) each hold a
capability proof that must verify and a seeded mutant that must fail at its own
declaration. This module runs them on an installed Verus and applies one rule:
a candidate qualifies only when its log reports the exact counts and the mutant
failure names the seeded region. It reads proof output and nothing else, so it
is analysis that belongs beside the shared prover tools, not a record of how or
when a run happened. Verus and Z3 come from the shared install-prover-tools
action (or `make install-verus` locally); nothing here installs them.

Run it with `uv run --script scripts/verus_probe.py`; `make verus` does.
"""

from __future__ import annotations

from pathlib import Path
import re
import shlex
import sys
import tempfile
from typing import Annotated

from cyclopts import App, Parameter

from captured_command import run_captured

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tools/verifier-fixtures/verus-wiring-probe"
VERUS_CANDIDATES = ("macro", "attributes", "companion", "single-root")
VERUS_FUNCTIONS = {
    "macro": ("capability", "mutant"),
    "attributes": ("capability", "mutant"),
    "companion": ("capability", "mutant"),
    "single-root": ("capability", "helper", "mutant"),
}
# The companion crate is a negative control: Verus rejects its wrapper because
# the production crate carries no specification, which is the finding that
# chose the other wirings. It must keep failing; a pass would mean it verified
# an executable body it has no contract for.
EXPECTED_QUALIFIED = frozenset({"macro", "attributes", "single-root"})


# Variables the verifier must not inherit. Verus sets its own toolchain, and
# cargo-verus makes `verus` the compiler driver, so a compiler wrapper such as
# sccache would sit in front of it and Verus refuses to start behind one.
# cuprum overlays variables and cannot unset one, so each command runs through
# `env -u`.
INHERITED_VARIABLES = ("RUSTUP_TOOLCHAIN", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER")


def _verus_environment(z3_path: Path) -> dict[str, str]:
    """Return the variables overlaid on the child environment.

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


def _refresh_candidate_fingerprint(directory: Path, candidate: str) -> None:
    """Touch the proof file before a build so cargo-verus reruns the selection.

    cargo-verus does not fingerprint the function-selection arguments, so a
    warm target directory would otherwise reuse another function's verdict.
    """
    (directory / f"{candidate}.rs").touch()


def _verus_command(
    binaries: Path,
    candidate: str,
    directory: Path,
    function: str,
    prover_tools: str,
) -> list[str]:
    """Return the verifier command for one candidate and one function.

    The ``helper`` selection verifies the shared implementation's own body.
    It needs ``--verify-only-module`` because ``--verify-root`` limits function
    selection to the root module, which excludes the included helper module.
    """
    if candidate == "single-root":
        if function == "helper":
            selection = (
                "--extra-arg=--verify-only-module=production",
                "--extra-arg=--verify-function=increment",
            )
        else:
            selection = (
                "--extra-arg=--verify-root",
                f"--extra-arg=--verify-function={function}",
            )
        return [
            *shlex.split(prover_tools),
            "verus",
            "run",
            "--repo-root",
            str(ROOT),
            "--proof-file",
            str(directory / "single-root.rs"),
            "--extra-arg=--crate-type=lib",
            *selection,
        ]
    selection = f"--verify-function={function}"
    command = [
        str(binaries / "cargo-verus"), "verus", "focus",
        "--manifest-path", str(directory / candidate / "Cargo.toml"),
    ]
    if candidate == "attributes":
        command += ["--features", "verus"]
    return command + ["--", "--verify-root", selection]


_BLOCK_END = re.compile(r"[{}]")
_FUNCTION_DECLARATION = re.compile(r"\bfn\s+(?P<name>\w+)")
_VERUS_LOCATION = re.compile(
    r"(?m)^error: postcondition not satisfied\n"
    r"\s*-->\s*(?P<path>.+?):(?P<line>\d+):(?P<column>\d+)$"
)


def _block_end(lines: list[str], start: int) -> int:
    """Return the zero-based line closing the function declared at ``start``.

    The fixture bodies hold no braces in comments or strings, so counting every
    brace character finds the declaration's end without parsing Rust. A
    declaration whose brace never closes reaches the end of the file and its
    verdict then fails qualification.
    """
    depth = 0
    opened = False
    for index in range(start, len(lines)):
        for character in _BLOCK_END.findall(lines[index]):
            if character == "{":
                depth += 1
                opened = True
            elif opened:
                depth -= 1
                if depth == 0:
                    return index
    return len(lines) - 1


def _mutant_region(source: Path) -> range:
    """Return the one-based lines belonging to the seeded mutant declaration.

    The region starts just after the preceding function's closing brace, so it
    includes the doc comments, attributes, and contract clause that Verus names
    when a postcondition fails, and ends at the mutant's own closing brace.

    Examples
    --------
    The diagnostic may point at a contract line above the body::

        _mutant_region(Path('macro.rs'))
        # range(11, 16) for the fixture's mutant declaration
    """
    lines = source.read_text(encoding="utf-8").splitlines()
    blocks = [
        (match["name"], index, _block_end(lines, index))
        for index, line in enumerate(lines)
        if (match := _FUNCTION_DECLARATION.search(line)) is not None
    ]
    for position, (name, _, end) in enumerate(blocks):
        if name == "mutant":
            start = 1 if position == 0 else blocks[position - 1][2] + 2
            return range(start, end + 2)
    raise RuntimeError(f"{source} has no seeded mutant")


def _fails_at_mutant(negative: str, source: Path, directory: Path) -> bool:
    """Report whether exactly one failure names the candidate's seeded mutant."""
    if negative.count("postcondition not satisfied") != 1:
        return False
    match = _VERUS_LOCATION.search(negative)
    if match is None:
        return False
    reported = Path(match["path"])
    if not reported.is_absolute():
        reported = directory / reported
    if reported.resolve() != source.resolve():
        return False
    return int(match["line"]) in _mutant_region(source)


def _reports_summary(log: str, verified: int, errors: int) -> bool:
    """Report whether a log's summary line records the exact counts."""
    pattern = rf"(?m)^verification results:: {verified} verified, {errors} errors(?: \(|$)"
    return re.search(pattern, log) is not None


def _helper_verified(output: Path) -> bool:
    """Report whether the single-root helper run discharged its own body."""
    helper = (output / "single-root-helper.log").read_text()
    selected = re.search(
        r"(?m)^note: verifying module production \(selected functions\)$", helper
    )
    return selected is not None and _reports_summary(helper, 1, 0)


def _qualified_candidates(
    output: Path, observations: list[dict], directory: Path
) -> list[str]:
    """Return candidates whose logs show exact counts and a located mutant."""
    qualified = []
    for candidate in VERUS_CANDIDATES:
        records = {
            item["function"]: item
            for item in observations
            if item["candidate"] == candidate
        }
        required = VERUS_FUNCTIONS[candidate]
        if not all(name in records for name in required):
            continue
        if any(records[name]["exit_code"] != 0 for name in required if name != "mutant"):
            continue
        if records["mutant"]["exit_code"] == 0:
            continue
        positive = (output / f"{candidate}-capability.log").read_text()
        negative = (output / f"{candidate}-mutant.log").read_text()
        if not _reports_summary(positive, 1, 0):
            continue
        if not _reports_summary(negative, 0, 1):
            continue
        if candidate == "single-root" and not _helper_verified(output):
            continue
        if not _fails_at_mutant(negative, directory / f"{candidate}.rs", directory):
            continue
        qualified.append(candidate)
    return qualified


def _capture(argv: list[str], log: Path, environment: dict[str, str]) -> dict:
    """Run one verifier command, keep its output as a log, and return its status.

    A command that cannot be started raises, so a missing verifier is reported
    as itself and not as a failed proof; a non-zero exit is an ordinary result
    here because the mutants are meant to fail.
    """
    result = run_captured(
        _without_inherited_variables(argv), cwd=FIXTURES, env=environment
    )
    log.write_text(result.output)
    print(f"{log.name}: exit {result.exit_code}", flush=True)
    return {"exit_code": result.exit_code}


def run_candidates(
    binaries: Path, z3_path: Path, prover_tools: str, output: Path
) -> list[str]:
    """Run every candidate's functions and return the candidates that qualify.

    Parameters
    ----------
    binaries : Path
        Installed Verus release directory that holds ``cargo-verus``.
    z3_path : Path
        The Z3 binary Verus is told to use.
    prover_tools : str
        Command prefix that invokes the shared ``prover-tools`` helper, which
        the single-root candidate runs through.
    output : Path
        Directory receiving one log per candidate and function.
    """
    environment = _verus_environment(z3_path)
    observations = []
    for candidate in VERUS_CANDIDATES:
        for function in VERUS_FUNCTIONS[candidate]:
            _refresh_candidate_fingerprint(FIXTURES, candidate)
            command = _verus_command(binaries, candidate, FIXTURES, function, prover_tools)
            observations.append(
                {
                    "candidate": candidate,
                    "function": function,
                    **_capture(command, output / f"{candidate}-{function}.log", environment),
                }
            )
    return _qualified_candidates(output, observations, FIXTURES)


def _companion_rejected_as_expected(output: Path) -> bool:
    """Report whether the companion crate failed for the reason it is a control.

    Its wrapper calls into the production crate, which carries no Verus
    specification, so Verus must say the callee "is not supported" and offer
    ``assume_specification``. Any other failure (a toolchain error, a missing
    solver) would also keep the companion from qualifying, and must not pass as
    the expected rejection.
    """
    log = (output / "companion-capability.log").read_text()
    return "is not supported" in log and "assume_specification" in log


def _show_unexpected_logs(output: Path, qualified: list[str]) -> None:
    """Print the logs of every candidate whose outcome was not the expected one.

    The logs may live in a temporary directory that is removed on return, so a
    failed job must read them here. An expected failure (the companion's, and
    every mutant's) stays quiet; only a candidate that should have qualified and
    did not, or should have been refused and was not, is shown.
    """
    surprising = EXPECTED_QUALIFIED.symmetric_difference(qualified)
    for candidate in VERUS_CANDIDATES:
        if candidate not in surprising:
            continue
        for log in sorted(output.glob(f"{candidate}-*.log")):
            print(f"--- {log.name} ---\n{log.read_text()}", flush=True)


app = App(name="verus_probe", help=__doc__)


@app.default
def probe(
    *,
    verus_dir: Path | None = None,
    z3: Annotated[Path | None, Parameter(env_var="VERUS_Z3_PATH")] = None,
    prover_tools: Annotated[str, Parameter(env_var="PROVER_TOOLS")] = "prover-tools",
    output: Path | None = None,
) -> int:
    """Run the wiring candidates on the installed Verus and compare the outcome.

    Exits non-zero unless exactly the macro, attributes and single-root
    candidates qualify, so a regression and an unexpected pass both fail. The
    logs of any candidate that surprised are printed before they are discarded.

    Parameters
    ----------
    verus_dir
        Installed Verus release directory; defaults to the release
        ``tools/verus/VERSION`` names under ``.verus``.
    z3
        The Z3 binary; read from ``VERUS_Z3_PATH``, which the shared install
        action sets.
    prover_tools
        Command prefix that invokes the shared ``prover-tools`` helper.
    output
        Directory to keep the logs in; a temporary one when omitted.
    """
    if z3 is None:
        raise SystemExit("set VERUS_Z3_PATH or pass --z3")
    version = (ROOT / "tools/verus/VERSION").read_text().strip()
    # The commands run from the fixture directory, so a relative path given
    # from the invoking directory would resolve against the wrong one.
    binaries = (verus_dir or ROOT / ".verus" / version / "verus").resolve()
    with tempfile.TemporaryDirectory() as scratch:
        logs = output or Path(scratch)
        logs.mkdir(parents=True, exist_ok=True)
        qualified = run_candidates(binaries, z3.resolve(), prover_tools, logs)
        companion_ok = _companion_rejected_as_expected(logs)
        matches = set(qualified) == EXPECTED_QUALIFIED and companion_ok
        if not matches:
            _show_unexpected_logs(logs, qualified)
            if not companion_ok:
                companion = (logs / "companion-capability.log").read_text()
                print(f"--- companion-capability.log ---\n{companion}", flush=True)
    print("Qualified wiring candidates: " + ", ".join(qualified))
    return 0 if matches else 1


if __name__ == "__main__":
    sys.exit(app())
