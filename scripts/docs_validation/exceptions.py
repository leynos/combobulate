"""Validate the trusted-boundary exception register (decision D02, ADR-0002, VO-3).

An exception is valid from its approval date until its `invalid_from` date, at
most 90 days, and never past its release-gate task (4.3.3 or 6.3.4). It names
a narrowed claim and an owner, and only the sponsor approves it. It never
satisfies a proof-required component: the evidence gate admits a record that
cites an active exception at `restricted` at best. Problems are named one by
one so a malformed exception is rejected for a specific reason.
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping

from jsonschema import Draft202012Validator

from .context import ValidationContext, require

MAXIMUM_LIFETIME = datetime.timedelta(days=90)


def exception_problems(entry: Mapping[str, object], sponsor: str, ticked: frozenset[str]) -> list[str]:
    """List every way an exception breaks D02; e.g. a 91-day lifetime gives 'lifetime-over-90-days'."""
    approved = datetime.date.fromisoformat(str(entry['approved_on']))
    invalid_from = datetime.date.fromisoformat(str(entry['invalid_from']))
    checks = [
        (invalid_from <= approved, 'empty-lifetime'),
        (invalid_from - approved > MAXIMUM_LIFETIME, 'lifetime-over-90-days'),
        (entry['approved_by'] != sponsor, 'approver-not-sponsor'),
        (not str(entry['narrowed_claim']).strip(), 'missing-narrowed-claim'),
        (not str(entry['owner']).strip(), 'missing-owner'),
        (entry['release_gate'] in ticked, 'past-release-gate'),
    ]
    return [problem for failed, problem in checks if failed]


def annotated_exceptions(register: Mapping[str, object], sponsor: str,
                         ticked: frozenset[str]) -> dict[str, dict[str, object]]:
    """Index exceptions by identifier with their problems attached, ready for the evidence gate."""
    return {str(entry['id']): dict(entry) | {'problems': exception_problems(entry, sponsor, ticked)}
            for entry in register['exceptions']}


def ticked_tasks(roadmap: Mapping[str, object]) -> frozenset[str]:
    """Return the identifiers of ticked roadmap tasks."""
    return frozenset(task['id'] for phase in roadmap['phases'] for step in phase['steps'] for task in step['tasks']
                     if task['status'] == 'done')


def check_exceptions(context: ValidationContext) -> None:
    """Require every committed exception to satisfy D02; an expired one is history, not a fault."""
    register = context.load('spec/exceptions.json')
    Draft202012Validator(context.load('spec/exception.schema.json'),
                         format_checker=Draft202012Validator.FORMAT_CHECKER).validate(register)
    sponsor = context.load('spec/decisions.json')['authorities']['roles']['sponsor']
    annotated = annotated_exceptions(register, sponsor, ticked_tasks(context.load('spec/roadmap.json')))
    require(len(annotated) == len(register['exceptions']), 'Duplicate exception identifier')
    for exception_id, entry in annotated.items():
        require(not entry['problems'], f"Exception {exception_id} breaks D02: {', '.join(entry['problems'])}")
    context.record('exceptions', 'Every exception has an owner, a narrowed claim, sponsor approval, a lifetime of at '
                                 'most 90 days, and an unpassed release gate.', len(annotated))
