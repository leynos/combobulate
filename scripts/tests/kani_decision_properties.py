"""State the properties VO-11b's decision must satisfy over the fact product.

The decision suite is only as strong as the relations it checks, so they live
here as small composable predicates rather than as loops buried in each test.
Each one is written in the direction the execplan states it: a claim that keeps
its assertion and its witness stands, a harness that does worse never improves
the outcome, and a failed claim assertion dominates everything below it.

Every property other than "an undeclared harness is a structural error" is
stated over *well-formed* combinations only — those whose every harness the
manifest declares. VO-11b makes a role-less harness a structural error, so a
combination containing one decides ``tool-error`` whatever else is true of it,
and holding a claim about outcomes to such a combination would test nothing but
the refusal that has its own test. Restricting the domain is what keeps each
property a statement about the decision rather than about the refusal.

Examples
--------
>>> len(list(every_combination())) > 10_000
True
>>> claims_stand((facts.HarnessFact('h::c', CLAIM, facts.SUCCESS),))
True
>>> declared_witnesses((facts.HarnessFact('h::c', CLAIM, facts.SUCCESS),))
()
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kani_decision_fixtures as facts
from docs_validation.kani_log import CLAIM, CONTROL

WITNESSES = ('satisfied', 'unsatisfied')
CONTROL_DISPOSITIONS = ('rejected-as-intended', 'rejected-otherwise', 'accepted', 'not-run')
# The statuses that leave a claim standing. A ``FAILURE`` stands only when the
# manifest asked for the panic and Kani's own note confirms it arrived.
STANDING = (facts.SUCCESS,)


def every_combination():
    """Yield every fact combination of one, two, and three harnesses."""
    for depth in (1, 2, 3):
        yield from facts.occurrences(depth)


def well_formed(combination) -> bool:
    """Report whether the manifest declares every harness in one combination."""
    return all(fact.role is not None for fact in combination)


def declared_combinations():
    """Yield the combinations VO-11b's outcome properties are stated over."""
    for combination in every_combination():
        if well_formed(combination):
            yield combination


def claims_of(combination) -> tuple:
    """Return the claim facts of one combination, in order."""
    return tuple(fact for fact in combination if fact.role == CLAIM)


def stands(fact) -> bool:
    """Report whether one claim fact leaves the claim proved.

    An unreachable witness denies it even when the assertion passed: a harness
    that assumed its own precondition away reports success having tested
    nothing.
    """
    excused = fact.status in STANDING or (fact.status == facts.FAILURE and fact.should_panic and fact.note)
    return excused and fact.cover != facts.UNREACHABLE


def claims_stand(combination) -> bool:
    """Report whether every claim in one combination stands, vacuously included.

    A run of only controls declares no claim, so nothing in it can fail to
    stand; the corpus's ``seeded_wrapping_mutant`` run is that shape and is
    correctly ``verified`` because its control did its job.
    """
    return all(stands(fact) for fact in claims_of(combination))


def witness_of(fact) -> str:
    """Return the status one claim's declared cover must report.

    A harness that never ran cannot have satisfied its cover, whatever the
    manifest declares, so absence is reported as ``unsatisfied`` — the same
    status an unreachable or unsatisfiable witness earns.
    """
    return 'satisfied' if fact.status != facts.ABSENT and fact.cover == facts.SATISFIED else 'unsatisfied'


def declared_witnesses(combination) -> tuple[str, ...]:
    """Return the witness statuses the manifest declares for one combination.

    Only a claim that names a cover contributes one. A claim with no cover has
    nothing to report, so its absence from the list is the property, not a gap
    in it.
    """
    return tuple(witness_of(fact) for fact in claims_of(combination) if fact.cover != facts.NOTHING)


def controls_well_formed(combination) -> bool:
    """Report whether one combination's controls each report one admitted disposition."""
    decision = facts.decision_for(combination)
    controls = [fact for fact in combination if fact.role == CONTROL]
    return (len(decision.negative_controls) == len(controls)
            and all(required and observed in CONTROL_DISPOSITIONS
                    for required, observed in decision.negative_controls))


def degrade(combination, index: int):
    """Replace one harness's behaviour with a worse one, keeping its identity.

    Degrading is the direction every property is stated in: a claim that failed,
    timed out, or never ran is worse than one that passed, and a control that
    timed out is worse than one that was rejected.
    """
    fact = combination[index]
    worse = facts.TIMEOUT if fact.role == CONTROL else facts.FAILURE
    replaced = facts.HarnessFact(fact.name, fact.role, worse, fact.cover, fact.expected,
                                 fact.should_panic, fact.note, fact.bounded, fact.cover_description)
    return combination[:index] + (replaced,) + combination[index + 1:]


def summarise(decision) -> tuple:
    """Reduce one decision to the facts the corpus records."""
    return (decision.outcome, decision.witness_statuses,
            decision.negative_controls, decision.run_mode)


def names_of(combination) -> list[str]:
    """Name the harnesses of one combination, for a readable test failure."""
    return [fact.name for fact in combination]
