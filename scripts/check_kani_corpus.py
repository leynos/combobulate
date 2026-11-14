#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["cuprum==0.1.0"]
# ///
"""Run the Kani corpus and check each run against the decision recorded for it.

The corpus in ``tools/verifier-fixtures/kani-corpus`` mixes harnesses that
verify with harnesses that fail on purpose (a counterexample, an unsatisfied
cover, an unwinding bound that is too small, a solver timeout). A green exit
status therefore means nothing here. Each run is instead decided with the Kani
log parser against the harness manifest, and the decision must equal the one
recorded for the same run in ``scripts/tests/fixtures/kani_logs/expected.json``,
with the exit status the run definition names. A Kani release that changes how
it reports any of them fails this check.

Run it from the repository root with Kani installed: ``make kani-corpus``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from captured_command import run_captured
from docs_validation.kani_log import (
    Decision,
    KaniLogError,
    decide,
    from_error,
    manifest_from_document,
    parse,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tools/verifier-fixtures/kani-corpus"
EXPECTED = ROOT / "scripts/tests/fixtures/kani_logs/expected.json"
# `truncated` is a run killed by an external timeout and `list` is an
# inventory; neither says anything about a harness's verdict.
NOT_VERDICT_RUNS = frozenset({"truncated", "list"})
HARNESS_FLAG = "--harness"


def selected_harnesses(arguments: list[str]) -> tuple[str, ...]:
    """Name the harnesses a run selects, in order; none means the whole crate.

    Examples
    --------
    ``selected_harnesses(['--harness', 'harnesses::verified', '--exact'])``
    returns ``('harnesses::verified',)``.
    """
    return tuple(
        arguments[index + 1]
        for index, token in enumerate(arguments)
        if token == HARNESS_FLAG and index + 1 < len(arguments)
    )


def recorded_decision(entry: dict) -> tuple:
    """Return a recorded decision in the order a ``Decision`` renders its facts."""
    return (
        entry["outcome"],
        tuple(entry["witnesses"]),
        tuple((bool(required), str(observed)) for required, observed in entry["controls"]),
        entry["run_mode"],
    )


def observed_decision(decision: Decision) -> tuple:
    """Return a fresh decision in the same order as :func:`recorded_decision`."""
    return (
        decision.outcome,
        tuple(decision.witness_statuses),
        tuple((bool(required), str(observed)) for required, observed in decision.negative_controls),
        decision.run_mode,
    )


def decide_log(text: str, selected: tuple[str, ...], manifest_document: dict) -> Decision:
    """Decide one log against the corpus manifest, narrowed to the run's selection."""
    manifest = manifest_from_document(manifest_document)
    try:
        log = parse(text)
    except KaniLogError as error:
        return from_error(error)
    return decide(log, manifest.select(selected) if selected else manifest)


def run_kani(arguments: list[str]) -> tuple[int, str]:
    """Run ``kani`` in the corpus crate and return its status and output.

    The front-end comes from ``KANI`` (default ``cargo-kani``), named directly
    so ``rustup`` does not install the repository's own toolchain first.
    """
    result = run_captured(
        [os.environ.get("KANI", "cargo-kani"), "kani", *arguments], cwd=CORPUS
    )
    return result.exit_code, result.output


def check_run(run: dict, recorded: dict, manifest_document: dict) -> list[str]:
    """Run one corpus entry and return the ways it disagreed with its record."""
    status, text = run_kani(run["arguments"])
    problems = []
    if status != run["expected_exit"]:
        problems.append(f"exit status {status}, expected {run['expected_exit']}")
    decision = decide_log(text, selected_harnesses(run["arguments"]), manifest_document)
    if observed_decision(decision) != recorded_decision(recorded[run["id"]]):
        problems.append(
            f"decided {observed_decision(decision)}, recorded {recorded_decision(recorded[run['id']])}"
        )
    return problems


def main() -> int:
    """Check every verdict-bearing corpus run and report each one."""
    runs = json.loads((CORPUS / "harnesses.json").read_text(encoding="utf-8"))["runs"]
    manifest_document = json.loads((CORPUS / "harness-manifest.json").read_text(encoding="utf-8"))
    recorded = json.loads(EXPECTED.read_text(encoding="utf-8"))["decisions"]
    failures = 0
    for run in (item for item in runs if item["id"] not in NOT_VERDICT_RUNS):
        problems = check_run(run, recorded, manifest_document)
        print(f"{run['id']}: {'ok' if not problems else 'FAILED'}", flush=True)
        for problem in problems:
            print(f"  {problem}", flush=True)
        failures += bool(problems)
    print(f"{len(runs) - len(NOT_VERDICT_RUNS) - failures} corpus runs matched, {failures} did not")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
