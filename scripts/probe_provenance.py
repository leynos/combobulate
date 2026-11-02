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
    ROOT,
    _digest,
    portable_argument,
    _require_command_statuses,
)

Z3_DISTRIBUTION = "z3-solver==4.16.0.0"


def _write_kani_provenance(
    directory: Path,
    route: str,
    reference: str,
    observations: list[dict],
    output_dir: Path,
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

    Examples
    --------
    The writer derives each digest from the files it names::

        _write_kani_provenance(directory, 'direct', reference, observations, output)
    """
    sources = [
        directory / name
        for name in (
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
        ]
    )
    provenance = {
        "tool": f"Kani {(ROOT / 'tools/kani/VERSION').read_text().strip()}",
        "route": route,
        "prover_tools_ref": reference,
        "stream_order": "captured stdout followed by captured stderr",
        "source_digests": {str(path.relative_to(ROOT)): _digest(path) for path in sources},
        "observations": observations,
    }
    (output_dir / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


def _write_verus_provenance(
    path: Path,
    version: str,
    z3_path: Path,
    banner: str,
    observations: list[dict],
) -> None:
    """Record the Verus and solver identities behind the observations.

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
    observations
        Captured candidate and function records.

    Examples
    --------
    The record binds the solver digest as well as its reported version::

        _write_verus_provenance(path, version, z3_path, banner, observations)
    """
    path.write_text(
        json.dumps(
            {
                "verus": version,
                "z3": portable_argument(str(z3_path)),
                "z3_distribution": Z3_DISTRIBUTION,
                "z3_version": banner,
                "z3_sha256": _digest(z3_path),
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
        status disagrees with the recorded expectation.

    Examples
    --------
    Exit status alone cannot qualify a corpus, so both checks run together::

        require_captured_output(observations)
    """
    if not observations or any(
        not (
            Path(item["log"]) if Path(item["log"]).is_absolute() else ROOT / item["log"]
        )
        .stat()
        .st_size
        for item in observations
    ):
        raise RuntimeError("missing verifier output cannot qualify a corpus")
    _require_command_statuses(observations)