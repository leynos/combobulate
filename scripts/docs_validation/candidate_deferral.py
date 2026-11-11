"""Reject a roadmap tick that outruns a candidate ADR subject deferred to it.

D07 settled most candidate ADR subjects in place and deferred the rest to the
roadmap item whose evidence will decide them. A tick claims that item is done.
While the deferral stands, the register says the subject is still waiting for
exactly that work, so the two records contradict each other. Nothing else reads
them together: the deferral is a decision-register field and the tick is a
roadmap status, and each existing check sees only its own file. That is how a
tick could land while its decision was still unwritten and every check pass.

The item may name a task (``1.2.1``) or a step (``2.4``), because D07 used
both. A step has no checkbox of its own, so it counts as ticked only when every
task beneath it is ticked; a partly finished step must not accuse a deferral of
being stale.
"""
from __future__ import annotations

from collections.abc import Mapping

from .context import ValidationContext, require


def _tasks(roadmap: dict) -> list[dict]:
    """Flatten the export to its task records; only ``ticked_items`` and its sibling call this."""
    return [task for phase in roadmap['phases'] for step in phase['steps'] for task in step['tasks']]


def ticked_items(roadmap: dict) -> set[str]:
    """Return every ticked task and every step whose tasks are all ticked.

    For example, a step whose only task is done contributes both identifiers::

        >>> roadmap = {'phases': [{'steps': [{'number': '2.4', 'tasks': [
        ...     {'id': '2.4.1', 'status': 'done'}]}]}]}
        >>> sorted(ticked_items(roadmap))
        ['2.4', '2.4.1']
    """
    ticked = {task['id'] for task in _tasks(roadmap) if task['status'] == 'done'}
    for phase in roadmap['phases']:
        for step in phase['steps']:
            identifiers = {task['id'] for task in step['tasks']}
            if identifiers and identifiers <= ticked:
                ticked.add(str(step['number']))
    return ticked


def roadmap_items(roadmap: dict) -> set[str]:
    """Return every task and step identifier the export declares.

    For example, the step identifier is declared alongside its task::

        >>> roadmap = {'phases': [{'steps': [{'number': '2.4', 'tasks': [
        ...     {'id': '2.4.1', 'status': 'open'}]}]}]}
        >>> sorted(roadmap_items(roadmap))
        ['2.4', '2.4.1']
    """
    steps = {str(step['number']) for phase in roadmap['phases'] for step in phase['steps']}
    return {task['id'] for task in _tasks(roadmap)} | steps


def deferred_candidates(register: dict) -> list[Mapping]:
    """Return the candidate ADR subjects whose disposition defers them to the roadmap.

    For example, the register's deferred candidates keep their deferral record::

        >>> register = {'candidate_adrs': [
        ...     {'id': 'CA1', 'disposition': {'kind': 'adr', 'adrs': ['ADR-0001']}},
        ...     {'id': 'CA3', 'disposition': {'kind': 'deferred', 'roadmap_item': '1.2.1'}}]}
        >>> [candidate['id'] for candidate in deferred_candidates(register)]
        ['CA3']
    """
    return [candidate for candidate in register['candidate_adrs']
            if candidate['disposition']['kind'] == 'deferred']


def _unknown_items(deferred: list[Mapping], declared: set[str]) -> list[str]:
    """Name each deferral whose roadmap item the export does not declare."""
    return [f"{candidate['id']} is deferred to {candidate['disposition']['roadmap_item']}, "
            f'which the roadmap does not declare'
            for candidate in deferred if candidate['disposition']['roadmap_item'] not in declared]


def _noutrun_items(deferred: list[Mapping], ticked: set[str]) -> list[str]:
    """Name each deferral whose roadmap item is already ticked."""
    return [f"{candidate['id']} ({candidate['subject']}) is deferred to "
            f"{candidate['disposition']['roadmap_item']}, which is ticked"
            for candidate in deferred if candidate['disposition']['roadmap_item'] in ticked]


def check_candidate_deferral(context: ValidationContext) -> None:
    """Require every deferred candidate to name work the roadmap has not yet ticked.

    Parameters
    ----------
    context
        Repository inputs; the checker reads the roadmap export and the
        decision register and nothing else.

    Returns
    -------
    None
        Records one result naming how many deferrals were checked against the
        roadmap's ticks.

    Raises
    ------
    AssertionError
        If a deferral names an item the roadmap does not declare, or names an
        item the roadmap reports as ticked. A typo would otherwise disable the
        check silently, and a tick would otherwise land ahead of the decision
        it is waiting on.
    """
    roadmap = context.load('spec/roadmap.json')
    deferred = deferred_candidates(context.load('spec/decisions.json'))
    unknown = _unknown_items(deferred, roadmap_items(roadmap))
    require(not unknown,
            'Deferred candidate ADR subject names an unknown roadmap item: '
            + '; '.join(unknown) + '. Correct the deferral or the roadmap identifier.')
    outrun = _noutrun_items(deferred, ticked_items(roadmap))
    require(not outrun,
            'Deferred candidate ADR subject outrun by a tick: ' + '; '.join(outrun)
            + '. Record its ADR before ticking the item, or move the deferral.')
    context.record('candidate-deferral',
                   f'{len(deferred)} deferred candidate ADR subjects name a roadmap item the export '
                   'declares and does not report as ticked.', len(deferred))
