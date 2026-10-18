"""Own roadmap task closure: a tick is an explicit claim the checker must back.

This module is the single owner of obligation-component satisfaction (MS-3)
and task closure (MS-4). A ticked task in `docs/roadmap.md` must have ticked
prerequisites, a completion record in `spec/task-completion.json` whose cited
decisions are accepted and whose artefacts resolve, and a satisfied component
for every proof obligation linked to it. Record-sourced components use admitted
evidence at the current binding. A task that meets every condition but is not
ticked is reported rather than failed, so a tick remains a deliberate claim.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from .context import ValidationContext, require
from .evidence_gate import Admission
from .evidence_records import admitted_evidence
from .markdown import headings
from .revision_reader import git_head_revision

ADMISSION_LEVELS = frozenset({'proof', 'bounded', 'tested'})
COMPONENT_ID = re.compile(r'^(PF[0-9]{2})\.([a-z][a-z0-9-]*)@([1-9][0-9]*\.[1-9][0-9]*\.[1-9][0-9]*)$')
CHECKER_SOURCE = 'checker:'
RECORD_SOURCE = 'record'


@dataclass(frozen=True)
class ArtefactProblem:
    """Name why one declared completion artefact cannot support a tick."""

    detail: str


@dataclass(frozen=True)
class CheckResult:
    """Bind one current-run design-check result to the source revision it inspected."""

    check: str
    status: str
    source_revision: str | None


@dataclass(frozen=True)
class ClosureInputs:
    """Bundle tasks, latest run results, bound evidence, and their resolvers."""

    tasks: Mapping[str, dict]
    completions: Mapping[str, dict]
    decisions: Mapping[str, dict]
    components: Mapping[str, list[dict]]
    check_results: tuple[CheckResult, ...]
    artefact_problem: Callable[[str], ArtefactProblem | None]
    evidence: Mapping[str, list[tuple[Admission, dict]]] = field(default_factory=dict)
    current_source_revision: str | None = None


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
    """Validate completion records; an ungoverned task may cite no decisions.

    For example, a known task with an artefact but no governing decision is
    still a valid completion record::

        >>> record = {'task': '1.1.1', 'decisions': [], 'artefacts': ['docs/guide.md']}
        >>> index_completions({'tasks': [record]}, {'1.1.1': {}}, {})
        {'1.1.1': {'task': '1.1.1', 'decisions': [], 'artefacts': ['docs/guide.md']}}
    """
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


def has_counterexample_for_revision(records: list[tuple[Admission, dict]], revision: str) -> bool:
    """Find a counterexample at one source revision regardless of its admission level."""
    return any(record['outcome'] == 'counterexample' and record['binding']['source_revision'] == revision
               for _, record in records)


def latest_check_result(results: tuple[CheckResult, ...], check: str) -> CheckResult | None:
    """Return the last result for a check in this validation run, if it ran."""
    return next((result for result in reversed(results) if result.check == check), None)


def _current_binding_records(records: list[tuple[Admission, dict]]) -> list[tuple[Admission, dict]]:
    """Keep only records whose admission matched the component's registered current binding."""
    stale_reasons = {'binding-stale', 'binding-incomplete'}
    return [(admission, record) for admission, record in records
            if not stale_reasons.intersection(admission.reasons)]


def _records_on_latest_date(records: list[tuple[Admission, dict]]) -> list[tuple[Admission, dict]]:
    """Select records on the newest date from a non-empty current-binding set."""
    latest_date = max(record['recorded_on'] for _, record in records)
    return [(admission, record) for admission, record in records if record['recorded_on'] == latest_date]


def record_component_failure(component: dict, records: list[tuple[Admission, dict]]) -> str | None:
    """Adjudicate record evidence for roadmap closure; only the component router calls this helper."""
    current_records = _current_binding_records(records)
    if not current_records:
        return f"component {component['id']} has no evidence record at the current binding"
    latest_records = _records_on_latest_date(current_records)
    latest_date = latest_records[0][1]['recorded_on']
    if len(latest_records) != 1:
        return f"component {component['id']} has {len(latest_records)} records on latest recorded_on date {latest_date}"
    admission, latest = latest_records[0]
    revision = latest['binding']['source_revision']
    if has_counterexample_for_revision(records, revision):
        return f"component {component['id']} has a counterexample at source revision {revision}"
    if admission.level.value not in component['accepts']:
        return f"component {component['id']} evidence is {admission.level.value} ({', '.join(admission.reasons)})"
    return None


def _checker_result_failure(component: dict, check_results: tuple[CheckResult, ...],
                            current_source_revision: str | None) -> str | None:
    """Check the latest in-run result, tested acceptance, and current source binding."""
    check = component['evidence_source'].removeprefix(CHECKER_SOURCE)
    if not current_source_revision:
        return f"component {component['id']} cannot determine the current source revision"
    if 'tested' not in component['accepts']:
        return f"component {component['id']} does not accept tested checker evidence"
    result = latest_check_result(check_results, check)
    if result is None or result.status != 'pass':
        return f"component {component['id']} needs the latest result for check {check} to pass in this run"
    if result.source_revision != current_source_revision:
        return f"component {component['id']} check {check} is not bound to current source revision " \
               f"{current_source_revision}"
    return None


def component_failure(component: dict, check_results: tuple[CheckResult, ...],
                      evidence: Mapping[str, list[tuple[Admission, dict]]],
                      current_source_revision: str | None) -> str | None:
    """Explain why a component is unsatisfied (MS-3), or return None when it is satisfied."""
    source = component['evidence_source']
    if source.startswith(CHECKER_SOURCE):
        records = evidence.get(component['id'], [])
        if current_source_revision and has_counterexample_for_revision(records, current_source_revision):
            return f"component {component['id']} has a counterexample at source revision {current_source_revision}"
        return _checker_result_failure(component, check_results, current_source_revision)
    return record_component_failure(component, evidence.get(component['id'], []))


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
        failures.extend(
            f'artefact {artefact} {problem.detail}'
            for artefact in record['artefacts']
            if (problem := inputs.artefact_problem(artefact)) is not None
        )
    failures.extend(failure for component in inputs.components.get(task_id, [])
                    if (failure := component_failure(component, inputs.check_results, inputs.evidence,
                                                     inputs.current_source_revision)) is not None)
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


def _anchor_problem(target: Path, anchor: str) -> ArtefactProblem | None:
    """Check a resolved Markdown file for one heading anchor; only the path resolver calls this."""
    try:
        text = target.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return ArtefactProblem('is not valid UTF-8 text')
    except OSError as error:
        return ArtefactProblem(f'cannot be read ({error})')
    try:
        has_anchor = anchor in headings(text)
    except ValueError as error:
        return ArtefactProblem(f'cannot be parsed ({error})')
    return None if has_anchor else ArtefactProblem(f'has no heading anchor {anchor!r}')


def artefact_resolver(context: ValidationContext) -> Callable[[str], ArtefactProblem | None]:
    """Resolve a repository artefact, returning a named problem when it cannot support a tick.

    A path may include a Markdown heading anchor, such as ``docs/guide.md#setup``.
    The callback returns ``None`` for a resolved artefact and ``ArtefactProblem``
    for paths outside the repository, missing files or anchors, and read or
    parse failures. This keeps filesystem errors outside the closure rules.

    For example, a file with a ``Setup`` heading resolves through
    ``artefact_resolver(context)('docs/guide.md#setup')`` with a ``None`` result.
    """
    root = context.root.resolve()

    def resolve(artefact: str) -> ArtefactProblem | None:
        """Resolve one path and translate expected filesystem failures to a problem."""
        path, _, anchor = artefact.partition('#')
        try:
            target = (root / path).resolve()
        except (OSError, RuntimeError) as error:
            return ArtefactProblem(f'cannot resolve path ({error})')
        if not target.is_relative_to(root):
            return ArtefactProblem('resolves outside the repository')
        if not target.is_file():
            return ArtefactProblem('does not resolve to a file')
        return _anchor_problem(target, anchor) if anchor else None

    return resolve


def check_task_status(context: ValidationContext, roadmap: dict, decisions: Mapping[str, dict],
                      components: Mapping[str, list[dict]]) -> None:
    """Require every tick to be backed by evidence from this run and its current source revision.

    Parameters
    ----------
    context
        The validation context; its earlier results decide checker-sourced components.
    roadmap
        The roadmap export, whose task ``status`` fields carry the ticks.
    decisions
        Decision records by identifier.
    components
        Validated obligation components by task identifier.
    Raises
    ------
    AssertionError
        When a ticked task fails any closure condition; the message lists each failure.
    """
    tasks = roadmap_tasks(roadmap)
    inputs = ClosureInputs(
        tasks=tasks,
        completions=index_completions(context.load('spec/task-completion.json'), tasks, decisions),
        decisions=decisions, components=components,
        check_results=tuple(CheckResult(str(row['check']), str(row['status']), context.source_revision)
                            for row in context.results),
        artefact_problem=artefact_resolver(context),
        evidence=admitted_evidence(context),
        current_source_revision=context.source_revision,
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
    requires_current_revision = any(component['evidence_source'].startswith(CHECKER_SOURCE)
                                    for task_components in components.values() for component in task_components)
    if requires_current_revision and context.source_revision is None:
        context.source_revision = git_head_revision(context.root)
    check_task_status(context, context.load('spec/roadmap.json'), decisions, components)
