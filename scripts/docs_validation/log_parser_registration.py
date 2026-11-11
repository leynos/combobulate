"""Require every registered log parser to prove its corpus reaches the classes it must (VO-13).

VO-13 makes registration a claim about evidence rather than a name in a list.
A parser is registered so the gate will trust it to re-derive a verdict, and the
gate's rejection rules key on outcomes the parser can actually report. A parser
whose corpus never produced a timeout cannot show it recognises one, so a
record that hit a resource limit would be decided by a rule the corpus never
exercised.

This check therefore reads the names in ``spec/evidence-reason-codes.json`` and
requires, for each one, that the committed corpus *decided through the parser*
reaches every class VO-13 names. It reads the decision, not the capture's own
label: ``harnesses.json`` records test intentions, and a label saying
``resource-exhausted`` proves only that whoever captured the log expected one.

Examples
--------
>>> required_classes({'verified', 'counterexample', 'resource-exhausted',
...                   'skipped', 'tool-error', 'unsupported'}, {'satisfied', 'unsatisfied'})
set()
>>> sorted(required_classes({'verified'}))
['counterexample', 'resource-exhausted', 'skipped', 'some-unsatisfied-witness', 'tool-error', 'unsupported-or-solver-unknown']
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from .context import ValidationContext, require

REGISTRY = 'spec/evidence-reason-codes.json'
CORPUS = 'scripts/tests/fixtures/kani_logs'
# The corpus family each registered name is proved by. A name with no family
# has no committed evidence this checker can read, which is a registration it
# cannot confirm rather than a corpus that happens to be elsewhere.
CORPORA = {'kani': CORPUS}
# Outcomes VO-13 requires. The undetermined class is a disjunction because two
# tools may report "could not decide" differently, and the requirement is that
# the parser distinguishes it from both success and disproof.
REQUIRED_OUTCOMES = frozenset({'verified', 'counterexample', 'resource-exhausted',
                               'skipped', 'tool-error'})
UNDETERMINED_OUTCOMES = frozenset({'unsupported', 'solver-unknown'})
# VO-13 names "some-unsatisfied witness" as its own class, and it is not an
# outcome: a cover can be unsatisfied while the run still reports ``verified``,
# which is precisely the gap VO-11b's non-vacuity log exists to expose. Reading
# only outcomes would let that log be deleted with the registration check still
# passing, so the witness statuses are scanned as a separate axis.
UNSATISFIED_WITNESS = 'some-unsatisfied-witness'


def required_classes(outcomes: Iterable[str], witness_statuses: Iterable[str] = ()) -> set[str]:
    """Return the VO-13 classes a corpus's decided outcomes leave uncovered.

    ``witness_statuses`` is the second axis: every status any declared cover
    reached. It defaults to empty so a caller that only holds outcomes still
    gets the outcome-level answer.

    Examples
    --------
    >>> sorted(required_classes({'verified', 'counterexample', 'resource-exhausted',
    ...                          'skipped', 'tool-error', 'unsupported'}, {'satisfied'}))
    ['some-unsatisfied-witness']
    """
    seen = set(outcomes)
    missing = set(REQUIRED_OUTCOMES - seen)
    if not seen & UNDETERMINED_OUTCOMES:
        missing.add('unsupported-or-solver-unknown')
    if 'unsatisfied' not in set(witness_statuses):
        missing.add(UNSATISFIED_WITNESS)
    return missing


def check_log_parser_registration(context: ValidationContext) -> None:
    """Require every registered parser's corpus to reach the classes VO-13 names.

    Parameters
    ----------
    context
        Repository inputs owned by the documentation checker.

    Returns
    -------
    None
        Records one result naming the parsers proved and the corpus behind each.

    Raises
    ------
    AssertionError
        If a registered name has no corpus this checker can read, or its corpus
        never decided one of the required classes.

    Examples
    --------
    With no parser registered the check passes vacuously and says so: the
    result counts zero parsers, which is what an empty registry should record.
    """
    registered = sorted(context.load(REGISTRY)['registered_log_parsers'])
    for name in registered:
        missing = _missing_classes(context.root, name)
        require(not missing,
                f'registered log parser {name!r} has no corpus log deciding '
                f'{sorted(missing)}; registration requires the classes VO-13 names')
    context.record('log-parser-registration',
                   'Every registered log parser has a committed corpus whose parsed decisions cover '
                   'the outcomes and the unsatisfied-witness class VO-13 requires.',
                   len(registered))


def _missing_classes(root: Path, name: str) -> set[str]:
    """Return the VO-13 classes one parser's corpus does not decide."""
    corpus = CORPORA.get(name)
    require(corpus is not None,
            f'registered log parser {name!r} has no committed corpus this check reads')
    decisions = _decisions(root / corpus)
    require(decisions, f'registered log parser {name!r} has a corpus that decides nothing')
    return required_classes(_axis(decisions, 'outcome'), _axis(decisions, 'witnesses'))


def _decisions(corpus: Path) -> list[Mapping[str, object]]:
    """Return the corpus's recorded decisions.

    ``expected.json`` holds what each log *decides*, which is why this reads it
    rather than ``harnesses.json``. The recorded decisions are the parser's
    output committed alongside the logs, so this check can run inside
    ``make design-check`` without a Kani installation.
    """
    document: Mapping[str, object] = json.loads(
        (corpus / 'expected.json').read_text(encoding='utf-8'))
    decisions = document['decisions']
    return [entry for entry in decisions.values() if isinstance(entry, Mapping)]


def _axis(decisions: list[Mapping[str, object]], field: str) -> set[str]:
    """Flatten one decision field into the set of values the corpus reaches."""
    reached: set[str] = set()
    for entry in decisions:
        value = entry.get(field)
        if isinstance(value, str):
            reached.add(value)
        elif isinstance(value, (list, tuple)):
            reached.update(str(item) for item in value)
    return reached
