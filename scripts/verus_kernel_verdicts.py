"""Decide whether a Verus log is the verdict a kernel candidate claims.

Three rules live here, one per tier of candidate. A positive run is admitted
only on exactly the pinned whole-crate count with no partial-verification
suffix. A mutant is admitted only when its exit status is 1, at least one error
was reported, every error is a postcondition failure inside that mutant's own
source region, and the intended clause is among the failures. A body-tier
mutant is admitted only when the run fails a loop invariant.

The rules are separated from the driver so that each can be read as a statement
about a log rather than as part of a subprocess pipeline. Nothing here runs a
solver, touches the filesystem beyond reading the mutant source, or writes a
record.
"""

from __future__ import annotations

import re
from pathlib import Path

# The pinned positive count. It is recorded, not predicted: a change to the
# shipped body or its specification moves it, and the run then fails until the
# new figure has been reviewed and written here.
POSITIVE_VERIFIED = 19

_SUMMARY = re.compile(
    r"(?m)^verification results:: (?P<verified>\d+) verified, (?P<errors>\d+) errors(?P<suffix>[^\n]*)$"
)
_LOCATION = re.compile(r"(?m)^\s*-->\s*(?P<path>.+?):(?P<line>\d+):(?P<column>\d+)$")
_CLAUSE = re.compile(r"(?m)^\s*(?P<clause>k[1-5])\(.*$")

# Errors that may accompany a verdict without disqualifying it. A rejection is
# still a compile that ran the verifier; anything else means the candidate
# never reached the obligation it was supposed to fail.
_PERMITTED = ("error: postcondition not satisfied", "error: aborting due to")


def _errors(log: str) -> list[str]:
    """Return the ``error:`` lines a Verus log reported."""
    return [line for line in log.splitlines() if line.startswith("error:")]


def _qualify_positive(log: str, exit_code: int) -> dict:
    """Check the positive run against the pinned count.

    Parameters
    ----------
    log
        The captured Verus output.
    exit_code
        The helper's exit status.

    Returns
    -------
    dict
        The verdict, naming the pinned count it admitted.

    Raises
    ------
    RuntimeError
        When the run failed, reported a partial verification, or verified any
        number other than the pinned one.
    """
    match = _SUMMARY.search(log)
    if match is None:
        raise RuntimeError("the positive run reported no verification summary")
    if match["suffix"].strip():
        raise RuntimeError(
            "the positive root must verify the whole crate, not a selection: "
            f"got {match['suffix'].strip()!r}"
        )
    if exit_code != 0 or match["errors"] != "0":
        raise RuntimeError(f"the positive run did not verify: exit {exit_code}")
    if int(match["verified"]) != POSITIVE_VERIFIED:
        raise RuntimeError(
            f"the positive root verified {match['verified']}, not the pinned "
            f"{POSITIVE_VERIFIED}; review the change and update the pin"
        )
    return {"kind": "positive", "verified": POSITIVE_VERIFIED}


def _qualify_mutant(log: str, exit_code: int, name: str, clauses: list[str],
                    source: Path) -> dict:
    """Check that one mutant failed its own clauses and nothing else.

    The failure locations are read from the compiled source, so the recorded
    clause is the one the diagnostic actually named rather than one the driver
    assumed.

    Parameters
    ----------
    log
        The captured Verus output.
    exit_code
        The helper's exit status.
    name
        The mutant's function name, used in every diagnostic here.
    clauses
        Clauses this mutant is required to violate.
    source
        The mutant root the diagnostic must point inside.

    Returns
    -------
    dict
        The verdict, naming the clauses and the lines they sit on.

    Raises
    ------
    RuntimeError
        When the verdict is not a located postcondition failure at the
        intended clause.
    """
    match = _SUMMARY.search(log)
    if match is None:
        raise RuntimeError(f"{name}: no verification summary was reported")
    if exit_code != 1:
        raise RuntimeError(f"{name}: expected exit 1, got {exit_code}")
    errors = _errors(log)
    if not errors:
        raise RuntimeError(f"{name}: no error was reported")
    unexpected = [line for line in errors if not line.startswith(_PERMITTED)]
    if unexpected:
        raise RuntimeError(f"{name}: disqualifying error {unexpected[0]!r}")
    located = _located_clauses(log, source)
    if not located:
        raise RuntimeError(f"{name}: no failure named a clause of its own region")
    reported = set(located.values())
    missing = [clause for clause in clauses if clause not in reported]
    if missing:
        raise RuntimeError(
            f"{name}: the failure named {sorted(reported)}, not the intended "
            f"{sorted(clauses)}"
        )
    return {"kind": "mutant", "clauses": clauses, "lines": located}


def _located_clauses(log: str, source: Path) -> dict[int, str]:
    """Map each failed clause line to the clause name written there.

    A diagnostic names a file and a line; the clause is whatever `k1` to `k5`
    call sits on that line of the mutant source. Reading it from the source
    means a reordered clause list cannot produce a false pass.
    """
    text = source.read_text(encoding="utf-8").splitlines()
    located: dict[int, str] = {}
    for match in _LOCATION.finditer(log):
        if Path(match["path"]).name != source.name:
            continue
        line = int(match["line"])
        if not 1 <= line <= len(text):
            continue
        clause = _CLAUSE.match(text[line - 1])
        if clause is not None:
            located[line] = clause["clause"]
    return located


def _qualify_body(log: str, exit_code: int) -> dict:
    """Check the body mutant failed a loop invariant and nothing else.

    Parameters
    ----------
    log
        The captured Verus output.
    exit_code
        The helper's exit status.

    Returns
    -------
    dict
        The verdict, naming the loop invariant that rejected the body.

    Raises
    ------
    RuntimeError
        When the wrap copy verified, or failed at some obligation other than a
        loop invariant.
    """
    match = _SUMMARY.search(log)
    if match is None:
        raise RuntimeError("the body mutant reported no verification summary")
    if exit_code != 1 or match["errors"] == "0":
        raise RuntimeError("the wrapping body must not verify")
    errors = _errors(log)
    unexpected = [
        line
        for line in errors
        if not line.startswith((*_PERMITTED, "error: invariant not satisfied"))
    ]
    if unexpected:
        raise RuntimeError(f"body mutant: disqualifying error {unexpected[0]!r}")
    if not any("invariant not satisfied" in line for line in errors):
        raise RuntimeError("the body mutant must fail a loop invariant")
    return {"kind": "body-mutant", "clause": "loop-invariant"}
