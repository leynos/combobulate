"""Validate roadmap dependencies, catalogue mappings, and generated ledgers."""
from __future__ import annotations

import re

from .context import ValidationContext, require
from .markdown import generated_matches


def collect_tasks(phases: list[dict]) -> tuple[dict[str, dict], set[int]]:
    """Index task contracts and design sections; repeated task IDs fail."""
    tasks: dict[str, dict] = {}
    sections: set[int] = set()
    for phase in phases:
        require(bool(phase['idea']) and bool(phase['gate']), 'Missing GIST hypothesis/gate')
        for step in phase['steps']:
            require(bool(step['question']), 'Missing step question')
            for task in step['tasks']:
                task_id = task['id']
                require(task_id not in tasks, f'Duplicate task {task_id}')
                require(task_id.startswith(step['number'] + '.'), f'Misnumbered task {task_id}')
                require(bool(task['success']) and bool(task['sections']), f'Missing task contract {task_id}')
                tasks[task_id] = task
                for start, end in re.findall(r'(\d+)(?:-(\d+))?', task['sections']):
                    sections.update(range(int(start), int(end or start) + 1))
    return tasks, sections


def check_dependencies(tasks: dict[str, dict]) -> None:
    """Require each dependency to exist earlier; this strict order proves acyclicity."""
    for task_id, task in tasks.items():
        for dependency in task['requires']:
            require(dependency in tasks, f'Unknown dependency {dependency} at {task_id}')
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


def check_generated_documents(context: ValidationContext, catalogue: list[dict], phases: list[dict]) -> None:
    """Check generated contents against masters, allowing only Markdown formatting."""
    inputs = [
        ('generate_reference.py', catalogue, 'docs/language-reference.md'),
        ('generate_roadmap.py', phases, 'docs/roadmap.md'),
        ('generate_bets.py', context.load('spec/bets.json')['bets'], 'docs/testable-bets.md'),
    ]
    for filename, source, path in inputs:
        generator = context.load_generator(filename)
        text = (context.root / path).read_text()
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
    check_generated_documents(context, catalogue, phases)
    check_task_links(context, tasks)
    context.record('catalogue', 'Unique IDs, scope labels, semantic table regeneration, and task mappings pass.', len(catalogue))
    context.record('roadmap', 'All tasks remain open, have success/design contracts, and form an acyclic earlier-dependency graph.', len(tasks))
    context.record('design-coverage', 'All 19 numbered design sections occur in task references; this is referential coverage, not proof of complete implementation scope.', len(sections))
