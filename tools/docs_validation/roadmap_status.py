"""Own roadmap task closure: a tick is an explicit claim the checker must back.

This module is the single owner of obligation-component satisfaction (MS-3)
and task closure (MS-4). A ticked task in `docs/roadmap.md` must have ticked
prerequisites, a completion record in `spec/task-completion.json` whose cited
decisions are accepted and whose artefacts resolve, and a satisfied component
for every proof obligation linked to it. A task that meets every condition but
is not ticked is reported rather than failed, so a tick remains a deliberate
claim. Until the evidence gate lands, record-sourced components fail closed.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .context import ValidationContext, require
from .markdown import headings

ADMISSION_LEVELS = frozenset({'proof', 'bounded', 'tested'})
COMPONENT_ID = re.compile(r'^(PF[0-9]{2})\.([a-z][a-z0-9-]*)@([1-9][0-9]*\.[1-9][0-9]*\.[1-9][0-9]*)$')
CHECKER_SOURCE = 'checker:'
RECORD_SOURCE = 'record'


@dataclass(frozen=True)
class ClosureInputs:
    """Bundle what closure reads; e.g. ClosureInputs(tasks, completions, decisions, components, passed, exists)."""

    tasks: Mapping[str, dict]
    completions: Mapping[str, dict]
    decisions: Mapping[str, dict]
    components: Mapping[str, list[dict]]
    passed_checks: frozenset[str]
    artefact_exists: Callable[[str], bool]


def roadmap_tasks(roadmap: dict) -> dict[str, dict]:
    """Index exported tasks in roadmap order; e.g. '1.1.1' maps to its task record."""
    return {task['id']: task for phase in roadmap['phases'] for step in phase['steps'] for task in step['tasks']}


def check_component(obligation: dict, component: dict) -> None:
    """Validate one component's identity, task link, levels, and evidence source."""
    match = COMPONENT_ID.match(component['id'])
    require(match is not None, f"Malformed component identity: {component['id']}")
    owner, method, task = match.groups()
    require(owner == obligation['id'], f"Component {component['id']} does not belong to {obligation['id']}")
    require(method == component['method'] and task == component['task'],
            f"Component {component['id']} disagrees with its method or task fields")
    require(task in obligation['tasks'], f"Component {component['id']} names a task outside {obligation['id']}")
    accepts = set(component['accepts'])
    require(bool(accepts) and accepts <= ADMISSION_LEVELS,
            f"Component {component['id']} must accept a non-empty subset of {sorted(ADMISSION_LEVELS)}")
    source = component['evidence_source']
    require(source == RECORD_SOURCE or source.startswith(CHECKER_SOURCE),
            f"Component {component['id']} has unknown evidence source {source!r}")
    require(not source.startswith(CHECKER_SOURCE) or 'tested' in accepts,
            f"Checker-sourced component {component['id']} must accept the tested level")


def index_components(obligations: list[dict]) -> dict[str, list[dict]]:
    """Validate every component and index them by task; every obligation task needs one."""
    by_task: dict[str, list[dict]] = {}
    seen: set[str] = set()
    for obligation in obligations:
        covered: set[str] = set()
        for component in obligation['components']:
            check_component(obligation, component)
            require(component['id'] not in seen, f"Duplicate component {component['id']}")
            seen.add(component['id'])
            covered.add(component['task'])
            by_task.setdefault(component['task'], []).append(component)
        missing = sorted(set(obligation['tasks']) - covered)
        require(not missing, f"{obligation['id']} has no component for tasks {', '.join(missing)}")
    return by_task


def index_completions(completion: dict, tasks: Mapping[str, dict], decisions: Mapping[str, dict]) -> dict[str, dict]:
    """Validate completion records; each names a known task, known decisions, and at least one artefact."""
    records: dict[str, dict] = {}
    for record in completion['tasks']:
        task_id = record['task']
        require(task_id in tasks, f'Completion record for unknown task {task_id}')
        require(task_id not in records, f'Duplicate completion record for {task_id}')
        unknown = sorted(set(record['decisions']) - set(decisions))
        require(not unknown, f"Completion record {task_id} cites unknown decisions {', '.join(unknown)}")
        require(bool(record['artefacts']), f'Completion record {task_id} lists no artefacts')
        records[task_id] = record
    return records


def component_failure(component: dict, passed_checks: frozenset[str]) -> str | None:
    """Explain why a component is unsatisfied (MS-3), or return None when it is satisfied."""
    source = component['evidence_source']
    if source.startswith(CHECKER_SOURCE):
        check = source.removeprefix(CHECKER_SOURCE)
        return None if check in passed_checks else f"component {component['id']} needs check {check} to pass"
    return f"component {component['id']} has no admitted evidence record (fail closed until the evidence gate)"


def closure_failures(task_id: str, inputs: ClosureInputs) -> list[str]:
    """List every MS-4 condition a task fails; an empty list means it may be ticked."""
    failures = [f'prerequisite {required} is not ticked' for required in inputs.tasks[task_id]['requires']
                if inputs.tasks[required]['status'] != 'done']
    record = inputs.completions.get(task_id)
    if record is None:
        failures.append('no completion record in spec/task-completion.json')
    else:
        failures.extend(f'decision {decision} is {inputs.decisions[decision]["lifecycle"]}, not accepted'
                        for decision in record['decisions'] if inputs.decisions[decision]['lifecycle'] != 'accepted')
        failures.extend(f'artefact {artefact} does not resolve' for artefact in record['artefacts']
                        if not inputs.artefact_exists(artefact))
    failures.extend(failure for component in inputs.components.get(task_id, [])
                    if (failure := component_failure(component, inputs.passed_checks)) is not None)
    return failures


def task_closure(inputs: ClosureInputs) -> tuple[list[str], list[str]]:
    """Check every ticked task and return (ticked, eligible-but-unticked) identifiers."""
    ticked: list[str] = []
    eligible: list[str] = []
    for task_id, task in inputs.tasks.items():
        failures = closure_failures(task_id, inputs)
        if task['status'] == 'done':
            require(not failures, f"Task {task_id} is ticked but {'; '.join(failures)}")
            ticked.append(task_id)
        elif not failures:
            eligible.append(task_id)
    return ticked, eligible


def artefact_resolver(context: ValidationContext) -> Callable[[str], bool]:
    """Resolve 'path' or 'path#anchor' beneath the root; a missing heading anchor does not resolve."""
    def exists(artefact: str) -> bool:
        path, _, anchor = artefact.partition('#')
        target = context.root / path
        if not target.is_file():
            return False
        return not anchor or anchor in headings(target.read_text(encoding='utf-8'))
    return exists


def check_task_status(context: ValidationContext, roadmap: dict, decisions: Mapping[str, dict],
                      components: Mapping[str, list[dict]]) -> None:
    """Require every tick to be backed by evidence; checker-sourced components read this run's results."""
    tasks = roadmap_tasks(roadmap)
    inputs = ClosureInputs(
        tasks=tasks,
        completions=index_completions(context.load('spec/task-completion.json'), tasks, decisions),
        decisions=decisions, components=components,
        passed_checks=frozenset(row['check'] for row in context.results if row['status'] == 'pass'),
        artefact_exists=artefact_resolver(context),
    )
    ticked, eligible = task_closure(inputs)
    context.record('roadmap-status',
                   f"{len(ticked)} of {len(tasks)} tasks ticked ({', '.join(ticked) or 'none'}); each tick has ticked "
                   'prerequisites, accepted decisions, resolvable completion artefacts, and satisfied obligation '
                   f"components. Eligible but unticked: {', '.join(eligible) or 'none'}.", len(ticked))


def check_roadmap_status(context: ValidationContext) -> None:
    """Run closure over the committed export; registered after every check whose result a component cites."""
    decisions = {record['id']: record for record in context.load('spec/decisions.json')['decisions']}
    components = index_components(context.load('spec/proof-obligations.json')['obligations'])
    check_task_status(context, context.load('spec/roadmap.json'), decisions, components)
