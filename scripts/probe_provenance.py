"""Record verifier probe provenance and reject empty captured output.

Only the verifier probe CLI uses these helpers. They keep the recorded source
digests, the calibrated solver pin, and the captured-output guard in one place
so both probe routes write the same record shape. Product code and the evidence
gate must not import this module.
"""

from __future__ import annotations

import json
from pathlib import Path

from verifier_probe_support import (
    KANI_SDK_TOOLCHAIN,
    ROOT,
    _digest,
    _digest_text,
    _installation_toolchain,
    portable_argument,
    _require_command_statuses,
    workspace_lint_tables,
)

Z3_DISTRIBUTION = "z3-solver==4.16.0.0"

VERUS_FIXTURE = ROOT / "tools/verifier-fixtures/verus-wiring-probe"

# The Verus record binds every input that can change a verdict: the proof and
# helper sources, the manifests and lockfile that select dependencies, and the
# probe modules that build and record the runs.
_VERUS_SOURCES = (
    "macro.rs",
    "attributes.rs",
    "companion.rs",
    "single-root.rs",
    "production.rs",
    "Cargo.toml",
    "Cargo.lock",
    "macro/Cargo.toml",
    "attributes/Cargo.toml",
    "companion/Cargo.toml",
    "production/Cargo.toml",
)
_VERUS_PROBE_SCRIPTS = (
    ROOT / "scripts/run_verifier_probes.py",
    ROOT / "scripts/verus_probe.py",
    ROOT / "scripts/probe_provenance.py",
    ROOT / "scripts/verifier_probe_support.py",
)


def _verus_sources() -> list[Path]:
    """Return the fixture inputs and generating scripts a verdict depends on.

    Examples
    --------
    The record names paths relative to the repository root::

        _verus_sources()[0]
        # PosixPath('.../tools/verifier-fixtures/verus-wiring-probe/macro.rs')
    """
    return [VERUS_FIXTURE / name for name in _VERUS_SOURCES] + list(_VERUS_PROBE_SCRIPTS)


def _write_kani_provenance(
    directory: Path,
    route: str,
    reference: str,
    observations: list[dict],
    output_dir: Path,
    installation: Path,
) -> None:
    """Record the tool, route, sources, and observations behind the corpus.

    Parameters
    ----------
    directory
        Fixture directory holding the harness sources and inventory.
    route
        Kani execution route used for every observation.
    reference
        Pinned ``rust-prover-tools`` revision.
    observations
        Captured subject records, including their expected exits.
    output_dir
        Directory receiving ``provenance.json``.
    installation
        Installed Kani release whose bundled toolchain is recorded.

    Examples
    --------
    The writer derives each digest from the files it names::

        _write_kani_provenance(directory, 'direct', reference, observations, output, install)
    """
    sources = [
        directory / name
        for name in (
            "Cargo.toml",
            "Cargo.lock",
            "src/lib.rs",
            "src/harnesses.rs",
            "harnesses.json",
            "kani-list.json",
        )
    ]
    sources.extend(
        [
            ROOT / "scripts/run_verifier_probes.py",
            ROOT / "scripts/kani_probe.py",
            ROOT / "scripts/verifier_probe_support.py",
            ROOT / "scripts/probe_provenance.py",
            # Cargo reads the repository configuration during the corpus build,
            # so a profile or target setting there can change what was built.
            ROOT / ".cargo/config.toml",
        ]
    )
    provenance = {
        "tool": f"Kani {(ROOT / 'tools/kani/VERSION').read_text().strip()}",
        # The toolchain the installed release declares, not the constant the
        # environment was built from: a release bundling a different nightly
        # then shows up as a provenance change rather than passing on a stale
        # claim. It is a declaration, so the driver's version check in
        # ``_kani_environment`` is what shows the observed release.
        "toolchain": _installation_toolchain(installation),
        "expected_toolchain_prefix": KANI_SDK_TOOLCHAIN,
        "route": route,
        "prover_tools_ref": reference,
        "stream_order": "captured stdout followed by captured stderr",
        "source_digests": {str(path.relative_to(ROOT)): _digest(path) for path in sources},
        # The ``in_place`` route copies the repository's lint tables into a
        # scratch manifest. Binding the extracted tables rather than the whole
        # root manifest keeps an unrelated dependency edit from forcing a
        # recapture while still covering the lints the probe actually applied.
        "lint_tables_sha256": _digest_text(
            workspace_lint_tables((ROOT / "Cargo.toml").read_text())
        ),
        "observations": observations,
    }
    (output_dir / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


def _write_verus_provenance(
    path: Path,
    version: str,
    z3_path: Path,
    banner: str,
    z3_distribution: str | None,
    observations: list[dict],
) -> None:
    """Record the Verus, solver, and source identities behind the observations.

    Parameters
    ----------
    path
        Destination ``provenance.json``.
    version
        Verus release selected for the run.
    z3_path
        Resolved, calibrated solver executable.
    banner
        Exact version banner the solver reported.
    z3_distribution
        The pinned distribution when its resolver supplied the executable, or
        ``None`` when the caller named the solver explicitly. The path and
        digest identify that solver without attributing it to the pin.
    observations
        Captured candidate and function records.

    Examples
    --------
    The record binds the solver digest, its sources, and the observations::

        _write_verus_provenance(path, version, z3_path, banner, None, observations)
    """
    path.write_text(
        json.dumps(
            {
                "verus": version,
                "z3": portable_argument(str(z3_path)),
                "z3_distribution": z3_distribution,
                "z3_version": banner,
                "z3_sha256": _digest(z3_path),
                "source_digests": {
                    str(source.relative_to(ROOT)): _digest(source)
                    for source in _verus_sources()
                },
                "observations": observations,
            },
            indent=2,
        )
        + "\n"
    )


def require_captured_output(observations: list[dict]) -> None:
    """Reject empty or missing captured output before recording a verdict.

    Parameters
    ----------
    observations
        Captured records whose ``log`` paths must exist and be non-empty.

    Raises
    ------
    RuntimeError
        If a record has no log or its log is empty, or if any captured exit
        status disagrees with the recorded expectation. An unreadable log —
        missing, or present but not statable — is reported through this same
        boundary, with the operating-system error chained so the original
        cause survives for diagnosis.

    Examples
    --------
    Exit status alone cannot qualify a corpus, so both checks run together::

        require_captured_output(observations)
    """
    if not observations:
        raise RuntimeError("missing verifier output cannot qualify a corpus")
    for item in observations:
        log = _captured_log(item)
        try:
            size = log.stat().st_size
        except OSError as error:
            raise RuntimeError(
                f"the captured output {log} could not be read: {error}"
            ) from error
        if not size:
            raise RuntimeError(f"the captured output {log} is empty")
    _require_command_statuses(observations)


def _captured_log(item: dict) -> Path:
    """Resolve one observation's log path exactly once.

    A recorded log is usually repository-relative, but an operator-supplied
    ``--output-dir`` can put it anywhere, so an absolute path is taken as
    given. Resolving in one place keeps the check and the diagnostic naming the
    same file.
    """
    log = Path(item["log"])
    return log if log.is_absolute() else ROOT / log
