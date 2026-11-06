"""Build and qualify the pinned Verus wiring observations.

Only the verifier probe CLI imports this module. It keeps solver resolution,
command construction, and mutant qualification together so the CLI stays
within the repository's module-size limit, and it is not an evidence parser.
"""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import re
import shlex
import shutil

from rust_prover_tools.commands import CommandSpec, run_command

from probe_provenance import Z3_DISTRIBUTION
from verifier_probe_support import ROOT

Z3_VERSION_BANNER = "Z3 version 4.16.0 - 64 bit"
VERUS_CANDIDATES = ("macro", "attributes", "companion", "single-root")
VERUS_FUNCTIONS = {
    "macro": ("capability", "mutant"),
    "attributes": ("capability", "mutant"),
    "companion": ("capability", "mutant"),
    "single-root": ("capability", "helper", "mutant"),
}


def _pinned_solver_executable() -> str | None:
    """Ask the pinned distribution where it installed the solver.

    ``uv tool run`` may consult a package index and unpack ``z3-solver`` into
    uv's cache, so this is a command-side effect rather than a lookup. It is
    therefore never a default: the probe CLI passes it as the resolver seam,
    and a caller that only needs the selection policy supplies its own.

    Returns
    -------
    str | None
        The executable ``uv`` reported, or ``None`` when it reported nothing.

    Raises
    ------
    RuntimeError
        When the pinned distribution could not be resolved. The record names
        the calibrated distribution, so a failed resolver must not fall back to
        whichever ``z3`` sits on ``PATH``: that binary would be recorded as the
        pin's own.
    """
    selected = run_command(
        CommandSpec(
            (
                "uv",
                "tool",
                "run",
                "--from",
                Z3_DISTRIBUTION,
                "python",
                "-c",
                "import shutil; print(shutil.which('z3') or '')",
            )
        )
    )
    if selected.exit_code != 0:
        raise RuntimeError(
            "the pinned z3-solver distribution could not be resolved: "
            f"{selected.stderr.strip() or 'uv exited with an error'}"
        )
    return selected.stdout.strip() or None


def select_solver(
    selection: str,
    *,
    pinned: Callable[[], str | None],
    discovery: Callable[[str], str | None] = shutil.which,
) -> tuple[Path, str | None]:
    """Choose the solver a selection names, without running anything.

    The selection policy and its side effects are separate steps: this
    function decides which executable a selection refers to, and the caller
    observes its version. ``pinned`` is a required parameter rather than a
    default because it is the one resolver that may consult a package index and
    write to uv's cache; a caller that only needs the policy still has to name
    the resolver it wants, so no innocuous-looking default can reach the
    network.

    Parameters
    ----------
    selection : str
        A solver name or path. The default ``z3`` name resolves the pinned
        ``z3-solver`` distribution, while any explicit selection is looked up
        as given. ``PATH`` is never consulted for the default: doing so would
        silently substitute an uncalibrated solver.
    pinned : Callable[[], str | None]
        Resolver for the pinned distribution. Supplied by the command boundary.
    discovery : Callable[[str], str | None]
        Lookup used for an explicit selection; a pure ``PATH``-style lookup by
        default.

    Returns
    -------
    tuple[Path, str | None]
        The selected executable and the pinned distribution when the resolver
        supplied it. An explicit selection records ``None``: its path and
        digest identify it, and attributing it to the pin would claim a source
        the probe never consulted.

    Raises
    ------
    RuntimeError
        When the selection resolves to no executable.

    Examples
    --------
    The default route names the pin, and an explicit path does not::

        select_solver('z3', pinned=lambda: '/pinned/z3')
        # (PosixPath('/pinned/z3'), 'z3-solver==4.16.0.0')
        select_solver('/opt/z3', pinned=lambda: '/pinned/z3')
        # (PosixPath('/opt/z3'), None)
    """
    solver = pinned() if selection == "z3" else discovery(selection)
    if solver is None:
        raise RuntimeError("the pinned Z3 executable is unavailable")
    distribution = Z3_DISTRIBUTION if selection == "z3" else None
    return Path(solver).resolve(), distribution


def qualify_solver(
    z3_path: Path,
    *,
    exit_code: int,
    reported: str,
    distribution: str | None,
) -> tuple[Path, str, str | None]:
    """Validate an observed solver invocation and name the recorded solver.

    The version command runs at the command boundary because it launches the
    resolved executable. This function receives its status and output, so
    qualification itself starts no process and a caller cannot mistake it for a
    step that does.

    Parameters
    ----------
    z3_path : Path
        Executable the selection resolved to.
    exit_code : int
        Exit status reported by ``z3_path --version``.
    reported : str
        Standard output of that invocation, already stripped.
    distribution : str | None
        Pinned distribution when its resolver supplied the executable.

    Returns
    -------
    tuple[Path, str, str | None]
        The validated executable, the exact banner it reported, and the
        distribution attribution. An explicit selection keeps ``None``: its
        path and digest identify it, and only the default resolver consults the
        pin.

    Raises
    ------
    RuntimeError
        When the run failed or its banner is not the calibrated one.

    Examples
    --------
    A calibrated banner is returned unchanged::

        qualify_solver(Path('/pinned/z3'), exit_code=0,
                       reported=Z3_VERSION_BANNER,
                       distribution=Z3_DISTRIBUTION)
        # (PosixPath('/pinned/z3'), 'Z3 version 4.16.0 - 64 bit', 'z3-solver==4.16.0.0')
    """
    if exit_code != 0 or reported != Z3_VERSION_BANNER:
        raise RuntimeError("the solver must report the calibrated Z3 4.16.0 release")
    return z3_path, reported, distribution



def _verus_environment(z3_path: Path) -> dict[str, str]:
    """Return the child environment that binds the calibrated solver."""
    environment = dict(os.environ)
    environment.pop("RUSTUP_TOOLCHAIN", None)
    environment["VERUS_Z3_PATH"] = str(z3_path)
    environment.update(
        RUSTFLAGS="-D warnings",
        CARGO_ENCODED_RUSTFLAGS="-D\x1fwarnings",
        CARGO_PROFILE_DEV_CODEGEN_BACKEND="llvm",
    )
    return environment


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
