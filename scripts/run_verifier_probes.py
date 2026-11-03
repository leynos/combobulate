#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["rust-prover-tools @ git+https://github.com/leynos/rust-prover-tools.git@9c4a27a86c678ceac1155404f45d95ee4a14a172"]
# ///
"""Capture tool capabilities without presenting them as product proofs.

For example, ``make kani-log-corpus`` captures labelled Kani subjects and
writes digest-bound provenance for later parser qualification.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from cyclopts import App

import verus_probe
from kani_probe import (
    kani_prefix, _kani_arguments, _kani_in_place_observation, _kani_observations,
)
from probe_provenance import (
    require_captured_output, _write_kani_provenance, _write_verus_provenance,
)
# The container recipe contract test reads it from this module.
from verifier_free_probe import run_verifier_free, _verifier_free_containerfile
from verifier_probe_support import (
    ROOT, FIXTURES, OUTPUT, _capture, _native_workspace,
)

app = App()


@app.command
def kani(
    *,
    prover_tools: str,
    installation: Path,
    route: str = "helper",
    only: str | None = None,
    output_dir: Path = OUTPUT,
) -> None:
    """Capture the Kani corpus through an explicitly recorded execution route.

    Parameters
    ----------
    prover_tools : str
        Command prefix that invokes the pinned prover helper.
    installation : Path
        Installed Kani release whose SDK and driver must be used.
    route : str
        ``helper`` captures through the helper, ``direct`` through the SDK.
    only : str | None
        Capture a single labelled subject and skip provenance.
    output_dir : Path
        Directory receiving the logs and provenance file.
    """
    reference = (ROOT / "tools/rust-prover-tools/REF").read_text().split("ref: ", 1)[1].splitlines()[0]
    directory = FIXTURES / "kani-corpus"
    environment = dict(os.environ)
    prefix, environment = kani_prefix(
        route, prover_tools, installation, directory, environment
    )
    definitions = json.loads((directory / "harnesses.json").read_text())
    observations = _kani_observations(
        definitions, prefix, route, directory, output_dir, environment, only
    )
    if only is None:
        observations.append(
            _kani_in_place_observation(
                prefix, route, _native_workspace(), output_dir, environment
            )
        )
        _write_kani_provenance(directory, route, reference, observations, output_dir)
    require_captured_output(observations)


@app.command
def verus(
    *,
    prover_tools: str,
    z3: str = "z3",
    output_dir: Path | None = None,
    verus_installation: Path | None = None,
) -> None:
    """Compare crate wiring with the helper's supported single-root route.

    Parameters
    ----------
    prover_tools : str
        Command prefix that invokes the pinned prover helper.
    z3 : str
        Solver selection; the default resolves the pinned distribution first.
    output_dir : Path | None
        Directory receiving the logs; defaults to the fixture observations.
    verus_installation : Path | None
        Installed Verus release; defaults to the pinned installation.
    """
    directory = FIXTURES / "verus-wiring-probe"
    version = (ROOT / "tools/verus/VERSION").read_text().strip()
    binaries = verus_installation or ROOT / ".verus" / version / "verus"
    z3_path, banner, z3_distribution = verus_probe.resolve_z3(z3)
    environment = verus_probe._verus_environment(z3_path)
    output = output_dir or directory / "observations"
    observations = []
    for candidate in verus_probe.VERUS_CANDIDATES:
        for function in verus_probe.VERUS_FUNCTIONS[candidate]:
            verus_probe._refresh_candidate_fingerprint(directory, candidate)
            observations.append(
                {
                    "candidate": candidate,
                    "function": function,
                    **_capture(
                        verus_probe._verus_command(
                            binaries, candidate, directory, function, prover_tools
                        ),
                        directory,
                        output / f"{candidate}-{function}.log",
                        environment,
                    ),
                }
            )
    provenance_path = (
        output / "provenance.json" if output_dir else directory / "provenance.json"
    )
    _write_verus_provenance(
        provenance_path, version, z3_path, banner, z3_distribution, observations
    )
    qualified = verus_probe._qualified_candidates(output, observations, directory)
    print("Qualified wiring candidates: " + ", ".join(qualified))
    if not qualified:
        raise RuntimeError(
            "no Verus candidate passed the exact count and located seeded mutant"
        )


@app.command
def verifier_free() -> None:
    """Build fixtures in a verifier-free container without bypassing host admission.

    Returns
    -------
    None
        Writes the verifier-free observation record.

    Raises
    ------
    RuntimeError
        If host admission rejects the environment or the verifier-free build
        fails.

    Examples
    --------
    The hosted observation job runs the command after a fresh runner boot::

        verifier_free()
    """
    run_verifier_free()


if __name__ == "__main__":
    app()
