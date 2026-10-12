"""Validate roadmap dependencies, catalogue mappings, and generated ledgers."""
from __future__ import annotations

import re
from types import ModuleType

from .context import ValidationContext, require, same_typed_value
from .markdown import generated_matches


def numbered_identity(value: object, name: str, components: int) -> tuple[int, ...]:
    """Parse a canonical positive numbered identity; '1.2' is a step, while '1.02' fails."""
    parts = value.split('.') if isinstance(value, str) else []
    require(len(parts) == components and all(re.fullmatch(r'[1-9][0-9]*', part) for part in parts),
            f'Malformed {name} identity: {value}')
    return tuple(map(int, parts))


def check_phase_order(phases: list[dict]) -> None:
    """Require unique ascending positive integer phases; [1, 2] passes, [2, 1] fails."""
    previous = 0
    for phase in phases:
        number = phase['number']
        require(type(number) is int and number > 0, f'Malformed phase number: {number}')
        require(number > previous, 'Phase numbers must be unique and ascending')
        previous = number


def check_step_hierarchy(phase: dict) -> None:
    """Bind ordered step identities to their phase; phase 1 cannot contain step '2.1'."""
    previous = 0
    for step in phase['steps']:
        parent, number = numbered_identity(step['number'], 'step', 2)
        require(parent == phase['number'], f'Misnumbered step {step["number"]} in phase {phase["number"]}')
        require(number > previous, f'Step numbers must be unique and ascending in phase {parent}')
        previous = number


def check_task_identity(task_id: str, step_number: str) -> None:
    """Bind canonical task identities to their step; task '1.2.1' cannot belong to step '1.1'."""
    phase, step, _ = numbered_identity(task_id, 'task', 3)
    require(f'{phase}.{step}' == step_number, f'Misnumbered task {task_id}')


def collect_tasks(phases: list[dict]) -> tuple[dict[str, dict], set[int]]:
    """Index task contracts and design sections; repeated task IDs fail."""
    tasks: dict[str, dict] = {}
    sections: set[int] = set()
    check_phase_order(phases)
    for phase in phases:
        check_step_hierarchy(phase)
        require(bool(phase['idea']) and bool(phase['gate']), 'Missing GIST hypothesis/gate')
        for step in phase['steps']:
            require(bool(step['question']), 'Missing step question')
            for task in step['tasks']:
                task_id = task['id']
                require(task_id not in tasks, f'Duplicate task {task_id}')
                check_task_identity(task_id, step['number'])
                require(bool(task['success']) and bool(task['sections']), f'Missing task contract {task_id}')
                tasks[task_id] = task
                for start, end in re.findall(r'(\d+)(?:-(\d+))?', task['sections']):
                    sections.update(range(int(start), int(end or start) + 1))
    return tasks, sections


def check_dependencies(tasks: dict[str, dict]) -> None:
    """Require dependencies earlier in both taxonomy and emitted task order; unrelated tasks can reorder."""
    positions = {task_id: position for position, task_id in enumerate(tasks)}
    for task_id, task in tasks.items():
        dependencies = task['requires']
        require(isinstance(dependencies, list) and all(type(dependency) is str for dependency in dependencies),
                f'Malformed dependencies at {task_id}: expected a string-ID list')
        for dependency in dependencies:
            require(dependency in tasks, f'Unknown dependency {dependency} at {task_id}')
            require(positions[dependency] < positions[task_id],
                    f'Dependency is not earlier in emitted task order: {task_id} -> {dependency}')
            require(tuple(map(int, dependency.split('.'))) < tuple(map(int, task_id.split('.'))),
                    f'Dependency is not earlier in this sequence: {task_id} -> {dependency}')


def check_catalogue(catalogue: list[dict], tasks: dict[str, dict]) -> None:
    """Validate vocabulary IDs and phase mappings; Core entries require phases 1–4."""
    ids: set[str] = set()
    for row in catalogue:
        require(row['id'] not in ids, f'Duplicate vocabulary ID {row["id"]}')
        ids.add(row['id'])
        require(row['scope'] in {'Core', 'Integration', 'Deferred'}, 'Bad scope')
        require(bool(row['roadmap_tasks']), f'Unmapped row {row["id"]}')
        for task_id in row['roadmap_tasks']:
            require(task_id in tasks, f'Unknown catalogue task {task_id}')
        if row['scope'] == 'Core':
            require(any(int(t.split('.')[0]) <= 4 for t in row['roadmap_tasks']),
                    f'Core row has no Core implementation task: {row["id"]}')


def check_roadmap_export(context: ValidationContext) -> None:
    """Require the committed JSON view to equal a fresh export of the canonical roadmap."""
    exporter = context.load_script('export_roadmap.py')
    try:
        fresh = exporter.parse_roadmap((context.root / 'docs/roadmap.md').read_text(encoding='utf-8'))
    except exporter.RoadmapStructureError as error:
        raise AssertionError(f'Malformed canonical roadmap: {error}') from error
    require(same_typed_value(context.load('spec/roadmap.json'), fresh),
            'Roadmap export drift: run scripts/export_roadmap.py')


def generated_documents(context: ValidationContext, catalogue: list[dict]) -> list[tuple[ModuleType, object, str]]:
    """List each generator module with its master data and generated document."""
    return [
        (context.load_generator('generate_reference.py'), catalogue, 'docs/language-reference.md'),
        (context.load_generator('generate_bets.py'), context.load('spec/bets.json')['bets'], 'docs/testable-bets.md'),
        (context.load_script('generate_decisions.py'), context.load('spec/decisions.json'), 'docs/decision-register.md'),
    ]


def check_generated_documents(context: ValidationContext, catalogue: list[dict]) -> None:
    """Check generated contents against masters, allowing only Markdown formatting."""
    for generator, source, path in generated_documents(context, catalogue):
        text = (context.root / path).read_text(encoding='utf-8')
        require(generated_matches(text, generator.render(source), generator.START, generator.END),
                f'Generated content drift: {path}')


def check_task_links(context: ValidationContext, tasks: dict[str, dict]) -> None:
    """Require open roadmap checkboxes and valid trace links; invented completion fails."""
    text = (context.root / 'docs/roadmap.md').read_text()
    require(not re.search(r'^- \[[xX]\]', text, re.M), 'Roadmap has fabricated completed tasks')
    actual = re.findall(r'^- \[ \] (\d+\.\d+\.\d+)\.', text, re.M)
    require(set(actual) == set(tasks) and len(actual) == len(tasks), 'Checkbox/task ledger mismatch')
    trace = context.load('spec/traceability.json')
    for group in ['requirements', 'verification']:
        for entry in trace[group]:
            require(bool(entry['tasks']), f'Unmapped trace entry {entry["id"]}')
            for task_id in entry['tasks']:
                require(task_id in tasks, f'Invalid trace task {task_id}')


def check_catalogue_and_roadmap(context: ValidationContext) -> None:
    """Run ledger checks; all 19 design sections must appear in task references."""
    catalogue = context.load('spec/vocabulary.json')['entries']
    phases = context.load('spec/roadmap.json')['phases']
    tasks, sections = collect_tasks(phases)
    check_dependencies(tasks)
    require(sections == set(range(1, 20)), f'Design coverage mismatch: {sections}')
    check_catalogue(catalogue, tasks)
    check_generated_documents(context, catalogue)
    check_roadmap_export(context)
    check_task_links(context, tasks)
    context.record('catalogue', 'Unique IDs, scope labels, semantic table regeneration, and task mappings pass.', len(catalogue))
    context.record('roadmap', 'All tasks remain open, have success/design contracts, and form an acyclic earlier-dependency graph.', len(tasks))
    context.record('design-coverage', 'All 19 numbered design sections occur in task references; this is referential coverage, not proof of complete implementation scope.', len(sections))
