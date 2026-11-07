"""Construct the per-harness facts the Kani decision suite enumerates.

VO-11b asks for an exhaustive enumeration, which is only exhaustive if the
generator is. Rather than sample a handful of handwritten logs, this module
names every *decision-relevant class* of per-harness fact — two facts belong to
the same class when no reader of ``decide`` can tell them apart — and the suite
takes the full cartesian product of those classes for one, two, and three
harnesses. Equality classes rather than raw field combinations is what makes
the product both complete and honest: adding a field the decision never reads
would multiply the cases without testing anything.

Nothing here may be more generous than a real log. A constructed block carries
the same fields the extractor fills, including summary counts, failure
explanations, and the echoed solver command, so a fact set the parser could
never produce is still refused rather than quietly accepted.

Examples
--------
>>> build((HarnessFact('h::c', CLAIM, SUCCESS),))[0].format
'regular'
>>> decide(*build((HarnessFact('h::c', CLAIM, SUCCESS),))).outcome
'verified'
"""
from __future__ import annotations

import itertools
import json
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.kani_log import (
    CLAIM, CONTROL, SUPPORTED_VERSIONS, FailedCheck, Harness, HarnessBlock, KaniLog, Manifest,
    ManualSummary, PropertyResult, decide,
)

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / 'scripts/tests/fixtures/kani_decision_table.json'
NOTHING = 'NONE'

SUCCESS = 'SUCCESS'
FAILURE = 'FAILURE'
TIMEOUT = 'TIMEOUT'
UNDETERMINED = 'UNDETERMINED'
UNWIND_FAILURE = 'UNWIND_FAILURE'
UNSUPPORTED_CHECK = 'UNSUPPORTED_CHECK'
UNSUPPORTED_ASSERTION = 'UNSUPPORTED_ASSERTION'
ABSENT = 'ABSENT'

SATISFIED = 'SATISFIED'
UNREACHABLE = 'UNREACHABLE'
UNSATISFIABLE = 'UNSATISFIABLE'
COVER_STATUSES = (NOTHING, SATISFIED, UNREACHABLE, UNSATISFIABLE)

AS_INTENDED = 'as-intended'
OTHERWISE = 'otherwise'

UNSUPPORTED_WORDING = 'TerminatorKind::InlineAsm is not currently supported by Kani.'
BOUNDED_SOLVER = '[Kani] Running: `cbmc --object-bits 16 --unwind 2 --sat-solver cadical`'
UNBOUNDED_SOLVER = '[Kani] Running: `cbmc --object-bits 16 --sat-solver cadical`'
FAILING = (FAILURE, AS_INTENDED, OTHERWISE, UNWIND_FAILURE, UNSUPPORTED_CHECK, UNSUPPORTED_ASSERTION)


@dataclass(frozen=True, slots=True)
class HarnessFact:
    """One harness reduced to the facts a decision reads; e.g. ``HarnessFact('h::c', CLAIM, SUCCESS)``.

    ``role`` is ``None`` for a harness the log reports but the manifest does not
    declare, which VO-11b calls a structural error. ``should_panic`` and
    ``note`` are separate because Kani's verdict note, not the manifest, is what
    excuses a failed assertion.
    """

    name: str
    role: str | None
    status: str
    cover: str = NOTHING
    expected: str = AS_INTENDED
    should_panic: bool = False
    note: bool = False
    bounded: bool = False
    cover_description: str | None = None

    @property
    def witness(self) -> str:
        """Name the cover this harness declares, if any."""
        return self.cover_description or f'the witness of {self.name}'

    @property
    def verdict(self) -> str:
        """Return the verdict Kani would print for this fact set."""
        if self.status in (SUCCESS, UNDETERMINED) or (self.status == FAILURE and self.should_panic and self.note):
            return 'SUCCESSFUL'
        return 'FAILED'


def _checks(fact: HarnessFact) -> list[PropertyResult]:
    """Build the checks this fact's block reports, in the order Kani lists them."""
    name = fact.name
    kind = {
        SUCCESS: ('assertion.1', 'SUCCESS', 'the assertion holds'),
        FAILURE: ('assertion.1', 'FAILURE', 'the assertion fails'),
        # A control's two dispositions are its *behaviour*: the seeded fault it
        # declares fired (assertion.1), or a different check did (assertion.2).
        AS_INTENDED: ('assertion.1', 'FAILURE', 'the seeded fault fires'),
        OTHERWISE: ('assertion.2', 'FAILURE', 'an unrelated check fails'),
        UNDETERMINED: ('assertion.1', 'UNDETERMINED', 'Kani could not decide this check'),
        UNWIND_FAILURE: ('unwind.0', 'FAILURE', 'unwinding assertion loop 0'),
        UNSUPPORTED_CHECK: ('unsupported_construct.1', 'FAILURE', UNSUPPORTED_WORDING),
        UNSUPPORTED_ASSERTION: ('assertion.1', 'FAILURE', UNSUPPORTED_WORDING),
    }.get(fact.status)
    checks = [PropertyResult(f'{name}.{kind[0]}', kind[1], kind[2])] if kind else []
    if fact.cover != NOTHING:
        checks.append(PropertyResult(f'{name}.cover.1', fact.cover, fact.witness))
    return checks


def block_of(fact: HarnessFact) -> HarnessBlock | None:
    """Build the harness block a log would report, or None when the harness is absent."""
    if fact.status == ABSENT:
        return None
    checks = _checks(fact)
    covers = tuple(item for item in checks if item.is_cover)
    failed = sum(1 for item in checks if item.status == 'FAILURE')
    block = HarnessBlock(
        name=fact.name,
        properties=checks,
        failed_count=None if fact.status == TIMEOUT else failed,
        total_count=None if fact.status == TIMEOUT else len(checks),
        other_count=sum(1 for item in checks if item.status == UNDETERMINED),
        other_kind='undetermined' if fact.status == UNDETERMINED else None,
        covered_satisfied=sum(1 for item in covers if item.status == SATISFIED) or None,
        covered_total=len(covers) or None,
        covered_unreachable=sum(1 for item in covers if item.status == UNREACHABLE) or None,
        verdict=fact.verdict,
        panics_as_expected=fact.should_panic and fact.note,
        solver_command=BOUNDED_SOLVER if fact.bounded else UNBOUNDED_SOLVER,
        seen_verification_time=fact.status != TIMEOUT,
        timed_out=fact.status == TIMEOUT,
        unwinding_reported=fact.status == UNWIND_FAILURE,
        has_results=fact.status != TIMEOUT,
    )
    if fact.status in FAILING:
        block.failures.append(FailedCheck(checks[0].description, 'src/harnesses.rs', 7))
    return block


def manifest_of(facts: Iterable[HarnessFact]) -> Manifest:
    """Build the manifest that declares exactly the harnesses with a role."""
    entries = []
    for fact in facts:
        if fact.role is None:
            continue
        covers = (fact.witness,) if fact.cover != NOTHING else ()
        expected = 'assertion.1' if fact.expected == AS_INTENDED else 'assertion.2'
        entries.append(Harness(fact.name, fact.role, covers,
                               expected if fact.role == CONTROL else None, fact.should_panic))
    return Manifest(tuple(entries))


def build(facts: Sequence[HarnessFact], *, format: str = 'regular',
          unsupported_constructs: tuple[str, ...] = ()) -> tuple[KaniLog, Manifest]:
    """Build one log and its manifest from a sequence of harness facts."""
    manifest = manifest_of(facts)
    if format != 'regular':
        return KaniLog(next(iter(SUPPORTED_VERSIONS)), format, (), None, unsupported_constructs), manifest
    blocks = tuple(block for block in (block_of(fact) for fact in facts) if block is not None)
    summary = ManualSummary(
        verified=sum(1 for block in blocks if block.verdict == 'SUCCESSFUL'),
        failures=sum(1 for block in blocks if block.verdict == 'FAILED'),
        total=len(blocks),
        failed=tuple(block.name for block in blocks if block.verdict == 'FAILED'),
    )
    return KaniLog(next(iter(SUPPORTED_VERSIONS)), format, blocks, summary, unsupported_constructs), manifest


def decision_for(facts: Sequence[HarnessFact], **options: Any):
    """Decide one constructed fact set, with the same options :func:`build` takes."""
    return decide(*build(facts, **options))


def claim_variants(name: str = 'h::c') -> tuple[HarnessFact, ...]:
    """Return one fact per decision-relevant class of claim harness.

    The classes are the outcomes Kani can print, each paired with the witness
    states a claim can declare, plus the two ``should_panic`` verdict shapes,
    plus the claim that never ran with and without a declared cover (an absent
    harness still has a cover the manifest names, and that cover is what VO-11b
    must report as unsatisfied).
    """
    outcomes = (HarnessFact(name, CLAIM, status) for status in
                (SUCCESS, FAILURE, TIMEOUT, UNDETERMINED, UNWIND_FAILURE, UNSUPPORTED_CHECK,
                 UNSUPPORTED_ASSERTION))
    witnesses = (HarnessFact(name, CLAIM, SUCCESS, cover) for cover in COVER_STATUSES[1:])
    panics = (HarnessFact(name, CLAIM, FAILURE, should_panic=True, note=note) for note in (True, False))
    absent = (HarnessFact(name, CLAIM, ABSENT, cover) for cover in (NOTHING, SATISFIED))
    return tuple(outcomes) + tuple(witnesses) + tuple(panics) + tuple(absent)


def control_variants(name: str = 'h::k') -> tuple[HarnessFact, ...]:
    """Return one fact per decision-relevant class of negative control.

    A control is judged by *how* it behaved, so its classes are the four ways it
    can be rejected (as intended, otherwise, by an unwinding failure alone,
    which is still otherwise), the two ways it can escape rejection (it passed,
    or it never ran), and the two undecided shapes.
    """
    return tuple(HarnessFact(name, CONTROL, status) for status in
                 (SUCCESS, AS_INTENDED, OTHERWISE, TIMEOUT, UNDETERMINED, ABSENT, UNWIND_FAILURE))


def undeclared_variant(name: str = 'h::u') -> HarnessFact:
    """Return the harness a log reports but no manifest declares."""
    return HarnessFact(name, None, SUCCESS)


def variants() -> tuple[HarnessFact, ...]:
    """Return every per-harness fact set the enumeration draws from."""
    return claim_variants() + control_variants() + (undeclared_variant(),)


def occurrences(depth: int) -> Iterator[tuple[HarnessFact, ...]]:
    """Yield every ordered fact combination of ``depth`` harnesses, with distinct names.

    Names are assigned by position, so two claim facts in one tuple describe two
    different harnesses rather than one harness reported twice, which the
    extractor refuses before a decision is ever taken.
    """
    for facts in itertools.product(variants(), repeat=depth):
        yield tuple(HarnessFact(f'h::{index}{fact.name.lstrip("h::")}', fact.role, fact.status,
                                fact.cover, fact.expected, fact.should_panic, fact.note,
                                fact.bounded, fact.cover_description)
                    for index, fact in enumerate(facts))


def table() -> dict[str, Any]:
    """Return VO-11b's decision table as data."""
    return json.loads(TABLE.read_text(encoding='utf-8'))


TABLE_STATUSES = {'UNSUPPORTED_FAILURE': UNSUPPORTED_CHECK}


def facts_of_row(row: dict[str, Any]) -> tuple[HarnessFact, ...]:
    """Translate one decision-table row into the facts that describe it.

    The table names statuses as a reader of a log would ("the check that
    failed"), while this module names them by the class the decision reads; the
    one place those differ is the failed ``unsupported_construct`` check.
    """
    facts = []
    for entry in row['harnesses']:
        covers = entry.get('covers') or ()
        facts.append(HarnessFact(
            name=entry['name'],
            role=entry.get('role'),
            status=TABLE_STATUSES.get(entry['status'], entry['status']),
            cover=entry.get('cover_status', NOTHING),
            expected=AS_INTENDED if entry.get('expected_failure') == 'assertion.1' else OTHERWISE,
            should_panic=bool(entry.get('should_panic')),
            note=bool(entry.get('panics_as_expected')),
            cover_description=covers[0] if covers else None,
        ))
    return tuple(facts)


def decide_row(row: dict[str, Any]):
    """Decide one decision-table row."""
    return decision_for(facts_of_row(row), format=row.get('format', 'regular'),
                        unsupported_constructs=tuple(row.get('unsupported_constructs', ())))
