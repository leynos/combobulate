"""Decide whether a Verus log is the verdict a kernel candidate claims.

Three rules live here, one per tier of candidate. A positive run is admitted
only on exactly the pinned whole-crate count with no partial-verification
suffix. A mutant is admitted only when its exit status is 1, every diagnostic it
reported is a postcondition failure inside that mutant's own source region, and
the intended clause is among the failures. A body-tier mutant is admitted only
when the run fails a loop invariant located in the mutated body.

Every rule reads the log as a list of diagnostics: an error text together with
the line it named, paired by :mod:`verus_kernel_diagnostic`. That pairing is
what lets a rule ask whether *this* failure happened where the candidate claims,
rather than whether the file was named somewhere in the log.

The rules are separated from the driver so that each can be read as a statement
about a log rather than as part of a subprocess pipeline. Nothing here runs a
solver, touches the filesystem beyond reading the mutant and body sources, or
writes a record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from verus_kernel_diagnostic import Diagnostic, diagnostics, texts

# The pinned positive count. It is recorded, not predicted: a change to the
# shipped body or its specification moves it, and the run then fails until the
# new figure has been reviewed and written here.
POSITIVE_VERIFIED = 20

_SUMMARY = re.compile(
    r"(?m)^verification results:: (?P<verified>\d+) verified, (?P<errors>\d+) errors(?P<suffix>[^\n]*)$"
)
_FUNCTION = re.compile(r"(?m)^\s*pub fn (?P<name>\w+)\s*\(")
_CLAUSE = re.compile(r"(?m)^\s*(?P<clause>k[1-5])\(.*$")

# Errors that may accompany a verdict without disqualifying it. A rejection is
# still a compile that ran the verifier; anything else means the candidate
# never reached the obligation it was supposed to fail.
_PERMITTED = ("error: postcondition not satisfied", "error: aborting due to")

# The obligations a mutated body may fail. An invariant failure is the verdict
# the body tier exists for. The body's own assertion beside the overflow test
# fails for the same reason: it states that the current position is out of
# range, which a wrapping sum detects at a different set of positions. Both are
# qualified on location, so an assertion anywhere else still disqualifies the
# run.
#
# A postcondition failure is deliberately absent, though the mutant tier admits
# one: the wrap root states no clauses of its own, so it has no postcondition to
# fail, and a log that reported one is describing some obligation the body tier
# never claimed. It is not permitted merely because the other tier permits it.
_BODY_PERMITTED = (
    "error: invariant not satisfied",
    "error: assertion failed",
    "error: aborting due to",
)


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
    an error the driver does not permit, a diagnostic outside the mutant's own
    region, or a failure at some clause other than the intended one.

    Raises
    ------
    RuntimeError
        When the log is not a rejection at the requested clauses.
    """
    found = diagnostics(log)
    _require_permitted(found, request, _PERMITTED)
    located = _located_clauses(found, request)
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


def _disqualifying(items: list[Diagnostic], permitted: tuple[str, ...]) -> list[str]:
    """Return the error texts outside ``permitted``, which no verdict admits.

    Both tiers ask the same question of a log — whether every error it
    reported is one its verdict allows — so the test lives in one place and
    each caller supplies the set it permits.
    """
    return [text for text in texts(items) if not text.startswith(permitted)]


def _require_permitted(
    items: list[Diagnostic], request: MutantRequest, permitted: tuple[str, ...]
) -> None:
    """Reject a log whose errors include one the mutant does not owe.

    A rejection is a compile that reached the verifier and failed an
    obligation. A type, syntax, or unsupported-feature error means the
    candidate never got that far, so it is not evidence whatever else the log
    says.

    Parameters
    ----------
    items
        The diagnostics the log reported.
    request
        The mutant whose name appears in the rejection message.
    permitted
        The error prefixes this tier admits. Each tier passes its own set, so a
        failure one tier owes is not thereby admitted by the other.

    Raises
    ------
    RuntimeError
        When no error was reported, or one is outside the permitted set.
    """
    if not items:
        raise RuntimeError(f"{request.name}: no error was reported")
    unexpected = _disqualifying(items, permitted)
    if unexpected:
        raise RuntimeError(f"{request.name}: disqualifying error {unexpected[0]!r}")


def _region(text: list[str], name: str) -> tuple[int, int]:
    """Return the first and last line of the mutant function called ``name``.

    The mutant root holds every seeded wrapper in one file, so a line number
    alone cannot say which mutant a diagnostic belongs to: `mutant_err` and
    `mutant_late` both state `k4`, and only their enclosing functions differ.
    The region runs from the function's own signature to the closing brace at
    column zero, which is the form every wrapper in this file takes.

    Raises
    ------
    RuntimeError
        When no function of that name is defined, since a verdict about a
        missing region would be a verdict about nothing.
    """
    starts = [
        index
        for index, line in enumerate(text, start=1)
        if (found := _FUNCTION.match(line)) is not None and found["name"] == name
    ]
    if not starts:
        raise RuntimeError(f"the mutant source defines no function {name!r}")
    start = starts[0]
    end = next(
        (line for line in range(start, len(text) + 1) if text[line - 1] == "}"),
        len(text),
    )
    return start, end


def _located_clauses(items: list[Diagnostic], request: MutantRequest) -> dict[int, str]:
    """Map each failed clause line to the clause name written there.

    A diagnostic names a file and a line; the clause is whatever `k1` to `k5`
    call sits on that line. Both facts are read from the source, and the line
    must fall inside the region of the mutant being verified, so a rejection
    reported for another wrapper in the same file cannot qualify this one.

    The region check is applied to every diagnostic, not only to the ones that
    name a clause: a permitted failure anywhere else means the run broke
    something it did not claim to break, and the record would attribute a
    confounded run to this mutant.

    Raises
    ------
    RuntimeError
        When a diagnostic falls outside the mutant's own region, or no function
        of the requested name exists in the source.
    """
    text = request.source.read_text(encoding="utf-8").splitlines()
    first, last = _region(text, request.name)
    located: dict[int, str] = {}
    for item in items:
        if item.is_abort_summary:
            continue
        line = item.location_in(request.source)
        if line is None:
            raise RuntimeError(
                f"{request.name}: {item.text!r} names no line of its own source, "
                "so it could have failed outside its own region"
            )
        if not first <= line <= last:
            raise RuntimeError(
                f"{request.name}: {item.text!r} at line {line} is outside its own "
                f"region ({first}-{last}), so it belongs to another wrapper"
            )
        clause = _CLAUSE.match(text[line - 1])
        if clause is not None:
            located[line] = clause["clause"]
    return located


def _qualify_body(log: str, exit_code: int, source: Path) -> dict:
    """Check the body mutant failed a loop invariant and nothing else.

    Parameters
    ----------
    log
        The captured Verus output.
    exit_code
        The helper's exit status.
    source
        The mutated body the invariant failure must be located in.

    Returns
    -------
    dict
        The verdict, naming the loop invariant that rejected the body.

    Raises
    ------
    RuntimeError
        When the wrap copy verified, or failed at some obligation other than
        the loop invariant its mutated overflow test breaks.
    """
    match = _SUMMARY.search(log)
    if match is None:
        raise RuntimeError("the body mutant reported no verification summary")
    if exit_code != 1 or match["errors"] == "0":
        raise RuntimeError("the wrapping body must not verify")
    _require_loop_invariant(diagnostics(log), source)
    return {"kind": "body-mutant", "clause": "loop-invariant"}


def _require_loop_invariant(items: list[Diagnostic], source: Path) -> None:
    """Reject a body mutant that failed at anything but its own obligations.

    An invariant error is only evidence about the mutated body when the
    diagnostic names a line inside it. A run that reported the failure without
    a location could have failed anywhere, including in the wrapper that is
    supposed to be unchanged, so the location is required rather than assumed.

    A mutation that replaces the overflow test also breaks the body's own proof
    assertion, which is an obligation about the mutated code that fails for the
    same reason the invariant does. It is admitted, but each diagnostic is
    qualified on its own: a located failure cannot account for a second one
    that merely repeats its wording, because the second names no line.

    A postcondition failure is not admitted here even though the seeded-mutant
    tier admits one. The generated wrap root states no clauses of its own, so
    the mutated body has nothing to fail a postcondition of; a log reporting
    one is describing an obligation this tier never claimed.

    Raises
    ------
    RuntimeError
        When an error is outside the permitted set, no loop invariant is among
        them, or a diagnostic names no line of the body.
    """
    request = MutantRequest("body mutant", [], source)
    _require_permitted(items, request, _BODY_PERMITTED)
    if not any("invariant not satisfied" in item.text for item in items):
        raise RuntimeError("the body mutant must fail a loop invariant")
    if not any("invariant not satisfied" in item.text and item.names(source) for item in items):
        raise RuntimeError("the body mutant's invariant failure must name a line of the body")
    unlocated = [
        item.text for item in items if not item.is_abort_summary and not item.names(source)
    ]
    if unlocated:
        raise RuntimeError(
            "the body mutant's failures must all be located in the body, but "
            f"{unlocated[0]!r} names no line of it"
        )
