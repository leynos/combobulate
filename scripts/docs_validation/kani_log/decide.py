"""Decide the admission facts a Kani log supports (VO-11b).

:mod:`docs_validation.kani_log.extract` says what a log contains; this module
says what that means for the evidence gate. The mapping is a pure function of
the parsed log and the record's harness manifest so a decision can be
re-derived from the same two inputs forever, and so the tests can enumerate
every combination of per-harness facts instead of sampling a few runs.

The manifest, not the log, supplies what a log cannot state itself: which
harnesses are claims and which are negative controls, what property each
control is supposed to fail, and which harnesses merely panic on purpose. DL-09
makes the same point about absence: a log cannot show what it omits, so a
manifest-bound claim set is what turns a missing harness into ``skipped``.

The precedence in :func:`decide` is the execplan's, ordered by how much the log
proved: a counterexample outweighs a timeout, which outweighs an undetermined
result, which outweighs a harness that never ran. ``bounds`` is always
``partial`` because DL-10 defers type-completeness to task 1.2.4, and
``run_mode`` is ``full-profile`` only when nothing could have been left out.

Expected failures are matched by *check identifier*, not by message. Kani
replaces an assertion message it cannot format with the placeholder
"This is a placeholder message; Kani doesn't support message formatted at
runtime", so matching prose would accept any failure at all; the identifier is
the only part of a check the harness author cannot accidentally change.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .extract import KaniLog, KaniLogError, PropertyResult, unwinding_checks_enabled
from .manifest import CLAIM, CONTROL, ROLES, Harness, Manifest
from .syntax import UNSUPPORTED_KIND, UNSUPPORTED_MARKER

VERIFIED = 'verified'
COUNTEREXAMPLE = 'counterexample'
RESOURCE_EXHAUSTED = 'resource-exhausted'
SOLVER_UNKNOWN = 'solver-unknown'
UNSUPPORTED = 'unsupported'
SKIPPED = 'skipped'
TOOL_ERROR = 'tool-error'
BOUNDS = 'partial'
FULL_PROFILE = 'full-profile'
FOCUSED = 'focused'
SATISFIED = 'satisfied'
UNSATISFIED = 'unsatisfied'
REJECTED_AS_INTENDED = 'rejected-as-intended'
REJECTED_OTHERWISE = 'rejected-otherwise'
ACCEPTED = 'accepted'
NOT_RUN = 'not-run'
INDETERMINATE_STATUSES = frozenset({'UNDETERMINED', 'UNREACHABLE'})


@dataclass(frozen=True, slots=True)
class Decision:
    """The admission facts a Kani run supports; e.g. ``Decision('verified', ...)``."""

    outcome: str
    bounds: str
    witness_statuses: tuple[str, ...]
    negative_controls: tuple[tuple[bool, str], ...]
    run_mode: str
    reason: str = ''

    def result(self) -> dict[str, object]:
        """Render the decision in the shape a ``VerifiedLogResult`` takes."""
        return {'outcome': self.outcome, 'bounds': self.bounds,
                'witness_statuses': self.witness_statuses,
                'negative_controls': self.negative_controls, 'run_mode': self.run_mode}


@dataclass(frozen=True, slots=True)
class _Observed:
    """What the log said about one harness, reduced to the facts a decision reads."""

    name: str
    succeeded: bool
    properties: tuple[PropertyResult, ...] = field(default_factory=tuple)
    failure_messages: tuple[str, ...] = field(default_factory=tuple)
    timed_out: bool = False
    panics_as_expected: bool = False

    @property
    def failures(self) -> tuple[PropertyResult, ...]:
        """Return this owner's checks that failed."""
        return tuple(item for item in self.properties if item.status == 'FAILURE')

    @property
    def unwinding_failures(self) -> tuple[PropertyResult, ...]:
        """Return this owner's failed unwinding assertions."""
        return tuple(item for item in self.failures if item.is_unwinding)

    @property
    def substantive_failures(self) -> tuple[PropertyResult, ...]:
        """Return this owner's failures that deny the claim rather than limit the run.

        Two kinds of failure are excluded. An unwinding failure says the bound
        was too small, not that the property is false, so VO-11b treats it as
        resource exhaustion. An ``unsupported_construct`` failure is Kani
        reporting it could not model the code at all, which is ``unsupported``
        and not evidence against the claim; counting it here would make every
        unsupported harness look like a counterexample.
        """
        return tuple(item for item in self.failures
                     if not item.is_unwinding and item.kind != UNSUPPORTED_KIND)

    @property
    def indeterminate(self) -> bool:
        """Report whether any of this owner's checks was left undecided.

        An ``UNREACHABLE`` cover counts. A harness that assumes its own
        precondition away reports ``0 of 0 failed`` and a successful verdict, so
        the unreachable witness is the only evidence that nothing was proved;
        excluding covers here would report that harness as ``verified``.
        """
        return any(item.status in INDETERMINATE_STATUSES for item in self.properties)


def decide(log: KaniLog, manifest: Manifest) -> Decision:
    """Map a parsed log and the manifest to the record facts Kani can support.

    Parameters
    ----------
    log
        Facts extracted from one Kani log.
    manifest
        The committed manifest for the verification run the log came from.

    Returns
    -------
    Decision
        ``outcome``, ``bounds``, witness statuses, negative controls, and
        ``run_mode``. Never raises: a log that cannot be decided from becomes
        ``tool-error``, which is what VO-11b asks for.

    Examples
    --------
    A single successful claim whose declared cover is satisfied decides
    ``('verified', 'partial', ('satisfied',), (), 'focused')`` even though its
    log also names an unreachable library assertion, because that assertion
    belongs to neither the harness nor the manifest.
    """
    try:
        return _decide(log, manifest)
    except ValueError as error:
        return Decision(TOOL_ERROR, BOUNDS, (), (), FOCUSED, reason=str(error))


def _decide(log: KaniLog, manifest: Manifest) -> Decision:
    """Apply the precedence table, raising ``ValueError`` for a structural mismatch."""
    if log.format != 'regular':
        raise ValueError(f'the log is {log.format!r} output, which carries no harness verdicts')
    observed = _observations(log, manifest)
    claims = [observed.get(item.name) for item in manifest.claims]
    controls = _control_statuses(manifest, observed)
    witnesses = _witness_statuses(manifest, observed)
    outcome = _outcome(log, claims, manifest)
    return Decision(outcome, BOUNDS, witnesses, controls, _run_mode(log, manifest),
                    reason='decided from the parsed log')


def _observations(log: KaniLog, manifest: Manifest) -> dict[str, _Observed]:
    """Attribute every reported check to a manifest harness, refusing a role-less one."""
    declared = set(manifest.names())
    observed: dict[str, _Observed] = {}
    for block in log.blocks:
        if block.name not in declared:
            raise ValueError(
                f'the log reports harness {block.name!r}, which the manifest does not declare')
        # Library checks are reported inside another harness's block. They belong
        # to no manifest harness, so nothing in the decision may read them;
        # surfacing one as a run failure would make every run look bad.
        observed[block.name] = _Observed(
            name=block.name, succeeded=block.succeeded,
            properties=block.owned(block.name),
            failure_messages=tuple(item.message for item in block.failures),
            timed_out=block.timed_out,
            panics_as_expected=block.panics_as_expected,
        )
    return observed


def _witness_statuses(manifest: Manifest, observed: dict[str, _Observed]) -> tuple[str, ...]:
    """Map each declared cover to the status Kani reported for it.

    The lookup is scoped to the claim that declares the cover. Two harnesses may
    reasonably describe their witnesses with the same words — the corpus has two
    runs of the same harness — so a global match would let one claim's satisfied
    cover stand in for another claim's unreachable one, which is exactly the
    vacuity this field exists to expose.
    """
    statuses = []
    for claim in manifest.claims:
        seen = observed.get(claim.name)
        reported = {item.description: item.status for item in (seen.properties if seen else ()) if item.is_cover}
        statuses.extend(SATISFIED if reported.get(cover) == 'SATISFIED' else UNSATISFIED
                        for cover in claim.covers)
    return tuple(statuses)


def _control_statuses(manifest: Manifest, observed: dict[str, _Observed]) -> tuple[tuple[bool, str], ...]:
    """Map each control to whether it was rejected, accepted, or never ran."""
    statuses = []
    for control in manifest.controls:
        seen = observed.get(control.name)
        if seen is None:
            statuses.append((True, NOT_RUN))
        elif seen.succeeded:
            statuses.append((True, ACCEPTED))
        elif _rejected_as_intended(control, seen):
            statuses.append((True, REJECTED_AS_INTENDED))
        else:
            statuses.append((True, REJECTED_OTHERWISE))
    return tuple(statuses)


def _rejected_as_intended(control: Harness, seen: _Observed) -> bool:
    """Report whether a control failed exactly the property the manifest expects.

    The manifest may name the check three ways, each a narrowing of the last:
    its full identifier, the property within the harness (``assertion.1``), or
    the check kind (``unwind``). Anything else is ``rejected-otherwise``,
    including a control that failed a different property of the same harness,
    because a seeded fault that trips an unrelated check has not shown the
    claim would be caught.
    """
    expected = (control.expected_failure or '').strip()
    return any(expected in (item.identifier, item.property, item.kind) for item in seen.failures)


def _outcome(log: KaniLog, claims: list[_Observed | None], manifest: Manifest) -> str:
    """Apply VO-11b's precedence, strongest disproof first.

    A harness that ran but is a ``should_panic`` claim has its failures treated
    as expected only when Kani's own verdict carries the note that a panic was
    encountered as expected; without that note the ordinary rules apply, so a
    manifest cannot talk the decision out of a real failure.
    """
    reported = [item for item in claims if item is not None]
    if any(_counts_as_counterexample(item, manifest) for item in reported):
        return COUNTEREXAMPLE
    if any(item.timed_out or item.unwinding_failures for item in reported):
        return RESOURCE_EXHAUSTED
    if any(_is_unsupported(log, item) for item in reported):
        return UNSUPPORTED
    if any(item.indeterminate for item in reported):
        return SOLVER_UNKNOWN
    if len(reported) != len(manifest.claims):
        return SKIPPED
    return VERIFIED


def _counts_as_counterexample(seen: _Observed, manifest: Manifest) -> bool:
    """Report whether this claim's failed property disproves the claim."""
    if not seen.substantive_failures:
        return False
    entry = next(item for item in manifest.claims if item.name == seen.name)
    return not (entry.should_panic and seen.panics_as_expected)


def _is_unsupported(log: KaniLog, seen: _Observed) -> bool:
    """Report whether Kani could not model a construct this harness reached.

    Three shapes say so, in decreasing strength. Kani may fail an
    ``unsupported_construct`` check, which is unambiguous. It may report the
    harness's own assertion as failed with a description naming the construct;
    the corpus's ``unsupported`` log is that shape, and only the description
    distinguishes it from a counterexample. Or it may list constructs it cannot
    model in its pre-flight warning, which alone proves nothing — the corpus's
    ``list`` log lists ``InlineAsm`` for a crate whose other harnesses verify —
    so the warning counts only when this harness was left undecided.
    """
    if any(item.kind == UNSUPPORTED_KIND for item in seen.properties):
        return True
    if any(UNSUPPORTED_MARKER in text.lower() for text in seen.failure_messages):
        return True
    return bool(log.unsupported_constructs) and seen.indeterminate


def _run_mode(log: KaniLog, manifest: Manifest) -> str:
    """Report ``full-profile`` only when nothing could have been left out.

    The coverage comparison is a *set* comparison, not a sequence one: VO-11b
    asks whether the record's claim set was covered, and Kani emits its blocks
    in an order of its own choosing regardless of the order ``--harness`` flags
    named them. Comparing positions would report a run that covered every
    harness as ``focused`` merely because the manifest listed them differently.
    Duplicates are still refused, so a log repeating one harness block cannot
    stand in for a missing one by padding its count.
    """
    observed = log.harnesses
    claimed = manifest.names()
    if len(set(observed)) != len(observed) or set(observed) != set(claimed):
        return FOCUSED
    if not all(unwinding_checks_enabled(block) for block in log.blocks):
        return FOCUSED
    return FULL_PROFILE


def from_error(error: KaniLogError) -> Decision:
    """Return the decision a structurally invalid log supports."""
    return Decision(TOOL_ERROR, BOUNDS, (), (), FOCUSED, reason=error.reason)
