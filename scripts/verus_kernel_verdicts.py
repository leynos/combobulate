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
from dataclasses import dataclass
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


@dataclass(frozen=True)
class MutantRequest:
    """What one mutant run claims, which its log must bear out.

    The request travels as one value because the fields are only meaningful
    together: a name without its clauses, or a clause list without the source
    it must be read from, would let a verdict qualify the wrong region.
    """

    name: str
    clauses: list[str]
    source: Path


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
    _require_whole_crate(match)
    _require_verified(match, exit_code)
    return {"kind": "positive", "verified": POSITIVE_VERIFIED}


def _require_whole_crate(match: re.Match) -> None:
    """Reject a run that verified a selection rather than the whole crate.

    Raises
    ------
    RuntimeError
        When the summary carries a partial-verification suffix.
    """
    if match["suffix"].strip():
        raise RuntimeError(
            "the positive root must verify the whole crate, not a selection: "
            f"got {match['suffix'].strip()!r}"
        )


def _require_verified(match: re.Match, exit_code: int) -> None:
    """Reject a run that did not verify the pinned number of obligations.

    Raises
    ------
    RuntimeError
        When the run failed, reported errors, or verified another count.
    """
    if exit_code != 0 or match["errors"] != "0":
        raise RuntimeError(f"the positive run did not verify: exit {exit_code}")
    if int(match["verified"]) != POSITIVE_VERIFIED:
        raise RuntimeError(
            f"the positive root verified {match['verified']}, not the pinned "
            f"{POSITIVE_VERIFIED}; review the change and update the pin"
        )


def _qualify_mutant(log: str, exit_code: int, request: MutantRequest) -> dict:
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
    request
        The mutant's name, the clauses it must violate, and the source its
        diagnostic must point inside.

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
        raise RuntimeError(f"{request.name}: no verification summary was reported")
    if exit_code != 1:
        raise RuntimeError(f"{request.name}: expected exit 1, got {exit_code}")
    located = _rejection_clauses(log, request)
    return {"kind": "mutant", "clauses": request.clauses, "lines": located}


def _rejection_clauses(log: str, request: MutantRequest) -> dict[int, str]:
    """Return the located clauses, once the log is a clean rejection of them.

    Every step below rejects a log that cannot be the failure the mutant owes:
    an error the driver does not permit, no failure inside the mutant's own
    region, or a failure at some clause other than the intended one.

    Raises
    ------
    RuntimeError
        When the log is not a rejection at the requested clauses.
    """
    _require_permitted(_errors(log), request)
    located = _located_clauses(log, request.source)
    if not located:
        raise RuntimeError(f"{request.name}: no failure named a clause of its own region")
    reported = set(located.values())
    missing = [clause for clause in request.clauses if clause not in reported]
    if missing:
        raise RuntimeError(
            f"{request.name}: the failure named {sorted(reported)}, not the intended "
            f"{sorted(request.clauses)}"
        )
    return located


def _disqualifying(errors: list[str], permitted: tuple[str, ...]) -> list[str]:
    """Return the error lines outside ``permitted``, which no verdict admits.

    Both tiers ask the same question of a log — whether every error it
    reported is one its verdict allows — so the test lives in one place and
    each caller supplies the set it permits.
    """
    return [line for line in errors if not line.startswith(permitted)]


def _require_permitted(errors: list[str], request: MutantRequest) -> None:
    """Reject a log whose errors include one the mutant does not owe.

    A rejection is a compile that reached the verifier and failed an
    obligation. A type, syntax, or unsupported-feature error means the
    candidate never got that far, so it is not evidence whatever else the log
    says.

    Raises
    ------
    RuntimeError
        When no error was reported, or one is outside the permitted set.
    """
    if not errors:
        raise RuntimeError(f"{request.name}: no error was reported")
    unexpected = _disqualifying(errors, _PERMITTED)
    if unexpected:
        raise RuntimeError(f"{request.name}: disqualifying error {unexpected[0]!r}")


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
    _require_loop_invariant(_errors(log))
    return {"kind": "body-mutant", "clause": "loop-invariant"}


def _require_loop_invariant(errors: list[str]) -> None:
    """Reject a body mutant that failed at anything but a loop invariant.

    Raises
    ------
    RuntimeError
        When an error is outside the permitted set, or no loop invariant is
        among them.
    """
    permitted = (*_PERMITTED, "error: invariant not satisfied")
    unexpected = _disqualifying(errors, permitted)
    if unexpected:
        raise RuntimeError(f"body mutant: disqualifying error {unexpected[0]!r}")
    if not any("invariant not satisfied" in line for line in errors):
        raise RuntimeError("the body mutant must fail a loop invariant")
