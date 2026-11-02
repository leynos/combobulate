"""Build and capture the Kani corpus commands used by the probe CLI.

The CLI in ``run_verifier_probes`` owns the probe command surface. This private
module owns how one Kani subject becomes a captured observation, so a route can
be read, composed, and tested without the command wiring around it. It is not a
public API: only the probe scripts may import it, and it must not enter the
evidence gate or product code.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from verifier_probe_support import _capture, _kani_environment, _native_workspace


def kani_prefix(
    route: str,
    prover_tools: str,
    installation: Path,
    directory: Path,
    environment: dict[str, str],
) -> tuple[list[str], dict[str, str]]:
    """Return the command prefix and child environment for a Kani route.

    Parameters
    ----------
    route : str
        Either ``helper`` for the pinned helper or ``direct`` for the SDK.
    prover_tools : str
        Command prefix that invokes the pinned prover helper.
    installation : Path
        Installed Kani release selected for the run.
    directory : Path
        Fixture directory passed to the helper as its working directory.
    environment : dict[str, str]
        Caller environment, copied and adjusted for the direct route.

    Returns
    -------
    tuple[list[str], dict[str, str]]
        The prefix and the environment the captured commands must receive.

    Raises
    ------
    ValueError
        When the route is neither ``helper`` nor ``direct``.
    """
    if route == "helper":
        return (
            [
                *shlex.split(prover_tools),
                "kani", "exec",
                "--installation", str(installation),
                "--cwd", str(directory),
            ],
            environment,
        )
    if route == "direct":
        return (
            [str(installation / "bin/kani-driver"), "kani"],
            _kani_environment(installation, environment),
        )
    raise ValueError("route must be helper or direct")


def _kani_arguments(subject: dict, route: str) -> list[str]:
    """Return one harness subject's arguments for the selected route."""
    if route == "helper":
        return [f"--extra-arg={argument}" for argument in subject["arguments"]]
    return subject["arguments"]


def _kani_observations(
    definitions: dict,
    prefix: list[str],
    route: str,
    directory: Path,
    output_dir: Path,
    environment: dict[str, str],
    only: str | None,
) -> list[dict]:
    """Capture every selected harness subject and return its observations."""
    observations = []
    for subject in definitions["runs"]:
        if only is not None and subject["id"] != only:
            continue
        command = [*prefix, *_kani_arguments(subject, route)]
        if subject.get("external_timeout"):
            command = ["timeout", "--signal=TERM", "8s", *command]
        observations.append(
            {
                "id": subject["id"],
                "expected_exit": subject["expected_exit"],
                **_capture(
                    command, directory, output_dir / f"{subject['id']}.log", environment
                ),
            }
        )
    return observations


def _kani_in_place_observation(
    prefix: list[str],
    route: str,
    scratch: Path,
    output_dir: Path,
    environment: dict[str, str],
) -> dict:
    """Run one completed harness against the scratch kernel/facade workspace."""
    scratch_prefix = list(prefix)
    if route == "helper":
        scratch_prefix[-1] = str(scratch)
    arguments = ["--harness", "verification::target_facts", "--exact", "--verbose"]
    if route == "helper":
        arguments = [f"--extra-arg={argument}" for argument in arguments]
    return {
        "id": "in_place",
        "expected_exit": 0,
        **_capture(
            [*scratch_prefix, *arguments],
            scratch,
            output_dir / "in_place.log",
            environment,
        ),
    }