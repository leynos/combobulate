"""Validate contracts claims in the design pack without claiming Rust evidence."""
from __future__ import annotations

import re
from jsonschema import Draft202012Validator, ValidationError
from .context import ValidationContext, require, unique_ids
from .markdown import MD


def check_kernel_envelope(context: ValidationContext) -> None:
    """Validate the envelope; removing validity from the example must fail."""
    schema = context.load('spec/kernel-contract.schema.json')
    Draft202012Validator.check_schema(schema)
    example = context.load('spec/kernel-contract.example.json')
    validator = Draft202012Validator(schema)
    validator.validate(example)
    broken = dict(example)
    broken.pop('validity')
    rejected = False
    try:
        validator.validate(broken)
    except ValidationError:
        rejected = True
    require(rejected, 'Missing-validity negative control was not rejected')
    context.record('kernel-contract-envelope', 'Draft 2020-12 schema and sample validate; missing-validity mutation is rejected. No claim about truth of native kernel metadata.', 1)


def check_bets_and_tasks(bets: list[dict], tasks: dict, requirement_ids: set[str]) -> None:
    """Validate planned bets and proof-first mappings; unrun bets cannot claim results."""
    bet_ids = {bet['id'] for bet in bets}
    require(len(bet_ids) == len(bets), 'Duplicate bet ID')
    for bet in bets:
        for key in ['hypothesis', 'success_witness', 'negative_control', 'falsifier',
                    'decision_rule', 'measurement']:
            require(bool(bet[key].strip()), f'Missing bet field {key}: {bet["id"]}')
        require(bet['status'] == 'planned-not-run', 'Fabricated experiment result')
        require(set(bet['requirements']) <= requirement_ids, 'Unresolved bet requirement')
        require(set(bet['tasks']) <= set(tasks), 'Unresolved bet task')
    for task in tasks.values():
        require(bool(task.get('proof_first')), f'No proof-first contract: {task["id"]}')
        require(bool(task.get('bets')) and set(task['bets']) <= bet_ids,
                f'Unresolved task bet: {task["id"]}')
    check_bet_links(bets, tasks)


def check_bet_links(bets: list[dict], tasks: dict) -> None:
    """Require bet and task links to agree both ways; e.g. B08 listing 1.1.4 needs 1.1.4 to cite B08."""
    for bet in bets:
        for task_id in bet['tasks']:
            require(bet['id'] in tasks[task_id]['bets'], f"Bet {bet['id']} lists task {task_id}, which does not cite it")
    listed = {(bet['id'], task_id) for bet in bets for task_id in bet['tasks']}
    for task in tasks.values():
        for bet_id in task['bets']:
            require((bet_id, task['id']) in listed, f"Task {task['id']} cites bet {bet_id}, which does not list it")


def check_obligations(context: ValidationContext, tasks: dict, verification_ids: set[str]) -> list[dict]:
    """Require substantive planned proof contracts; evidence remains absent at design time."""
    obligations = context.load('spec/proof-obligations.json')['obligations']
    require(len({o['id'] for o in obligations}) == len(obligations), 'Duplicate proof ID')
    for obligation in obligations:
        require(set(obligation['tasks']) <= set(tasks), 'Unresolved proof task')
        require(set(obligation['verification']) <= verification_ids, 'Unresolved proof verification ID')
        require(bool(obligation['property']) and bool(obligation['scope'])
                and bool(obligation['non_vacuity']), 'Incomplete proof contract')
        require(obligation['status'] == 'planned-not-run' and obligation['evidence'] is None,
                'This design pack must not fabricate a proof result')
        require({'Verus', 'Kani'} & set(obligation['tools']), 'No selected verifier')
    return obligations


def check_design_trace(context: ValidationContext, phases: list[dict], trace: dict) -> None:
    """Resolve design rows and goal links; table alignment has no semantic effect."""
    requirement_ids = unique_ids(trace['requirements'], 'requirement')
    verification_ids = unique_ids(trace['verification'], 'verification')
    design = (context.root/'docs/technical-design.md').read_text()
    tor = (context.root/'docs/terms-of-reference.md').read_text()
    for rid in requirement_ids:
        require(re.search(r'^\|\s*' + re.escape(rid) + r'\s*\|', design, re.M), f'Missing requirement row {rid}')
    for vid in verification_ids:
        require(re.search(r'^\|\s*' + re.escape(vid) + r'\s*\|', design, re.M), f'Missing verification row {vid}')
    declared_goals = re.findall(r'^\|\s*(G\d+)\s*\|', tor, re.M)
    goals = set(declared_goals)
    require(len(goals) == len(declared_goals), 'Duplicate goal ID')
    for phase in phases:
        require(set(phase['goals']) <= goals, f'Unresolved phase goals {phase["number"]}')
    for entry in trace['requirements']:
        require(set(entry['goals']) <= goals, f'Unresolved requirement goals {entry["id"]}')


SOURCE_ID = r'[ED]-[A-Z][A-Z0-9-]*'
SOURCE_WORD = rf'(?<![A-Z0-9-])({SOURCE_ID})(?![A-Z0-9-])'


def bracket_citations(text: str) -> set[str]:
    """Extract explicit citation groups; '[e-polars-null, d-tor]' declares two source IDs."""
    citations: set[str] = set()
    for group in re.findall(r'\[([^\[\]]+)\]', text):
        ids = [value.strip() for value in group.split(',')]
        if all(re.fullmatch(SOURCE_ID, value, re.I) for value in ids):
            citations.update(ids)
    return citations


def source_citations(text: str, source_ids: set[str]) -> set[str]:
    """Detect coded references without classifying ordinary e-commerce as a source.

    Known IDs retain canonical spelling checks in prose, code, tables and link
    labels. Unknown uppercase IDs and explicit bracket citation groups remain
    checked. Markdown word links such as '[e-commerce](url)' remain ordinary text.
    """
    citations: set[str] = set()
    for token in MD.parse(text):
        if token.type != 'inline':
            continue
        visible = ''.join(child.content if child.type in {'text', 'code_inline'} else ' '
                          for child in token.children or [])
        candidates = re.findall(SOURCE_WORD, visible, re.I)
        citations.update(value for value in candidates if value.isupper() or value.upper() in source_ids)
        citations.update(bracket_citations(visible))
    return citations


def check_backend_capabilities(context: ValidationContext) -> set[str]:
    """Resolve sources and refusal rules; documentation never enables unrun probes."""
    refs = (context.root/'docs/references.md').read_text()
    declared_sources = re.findall(r'^### ((?:E|D)-[A-Z0-9-]+)\s*$', refs, re.M | re.I)
    for sid in declared_sources:
        require(sid == sid.upper(), f'Noncanonical source ID {sid}: {context.root / "docs/references.md"}')
    source_ids = set(declared_sources)
    require(len(source_ids) == len(declared_sources), 'Duplicate source ID')
    for path in context.markdown_paths():
        for sid in source_citations(path.read_text(), source_ids):
            require(sid == sid.upper(), f'Noncanonical source ID {sid}: {path}')
            require(sid in source_ids, f'Unknown source ID {sid}: {path}')
    capabilities = context.load('spec/backend-capabilities.json')
    require(capabilities['selected_rust_revision'] is None, 'Unselected backend was pinned fictitiously')
    cap_ids = set()
    for cap in capabilities['capabilities']:
        require(cap['id'] not in cap_ids, 'Duplicate capability ID')
        cap_ids.add(cap['id'])
        require(set(cap['sources']) <= source_ids, 'Unresolved capability source')
        require(cap['rust_probe_status'] == 'not-run' and cap['eligible'] is False,
                'Documentation alone cannot enable an untested Rust capability')
        require(bool(cap['probe']) and bool(cap['refusal_rule']), 'Incomplete capability probe')
    return cap_ids


def check_revision_contracts(context: ValidationContext) -> None:
    """Check proposed contracts and report planned coverage, not verifier evidence."""
    phases = context.load('spec/roadmap.json')['phases']
    tasks = {t['id']: t for p in phases for step in p['steps'] for t in step['tasks']}
    bets = context.load('spec/bets.json')['bets']
    trace = context.load('spec/traceability.json')
    requirement_ids = unique_ids(trace['requirements'], 'requirement')
    verification_ids = unique_ids(trace['verification'], 'verification')
    check_bets_and_tasks(bets, tasks, requirement_ids)
    obligations = check_obligations(context, tasks, verification_ids)
    check_design_trace(context, phases, trace)
    cap_ids = check_backend_capabilities(context)
    context.record('testable-bets', 'Every bet has a witness, negative control, falsifier, decision rule, and resolved task/requirement links; all remain planned.', len(bets))
    context.record('proof-first-task-coverage', 'Every implementation or decision task has an explicit proof-first contract and bet mapping. This is planned coverage, not proof discharge.', len(tasks))
    context.record('proof-obligations', 'Properties, scopes, tool choices, non-vacuity controls, and task/V links resolve; no proof result is fabricated.', len(obligations))
    context.record('backend-capability-plans', 'All source IDs and probe/refusal contracts resolve; no unrun backend capability is marked eligible.', len(cap_ids))


def check_proof_evidence_envelope(context: ValidationContext) -> None:
    """Validate the planned record against schema version 2; records breaking the validity predicate fail."""
    import copy
    schema = context.load('spec/proof-evidence.schema.json')
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    example = context.load('spec/proof-evidence.example.json')
    validator.validate(example)

    def mutant(**changes: object) -> dict:
        record = copy.deepcopy(example)
        for path, value in changes.items():
            target = record
            *parents, leaf = path.split('__')
            for parent in parents:
                target = target[parent]
            if value is KeyError:
                del target[leaf]
            else:
                target[leaf] = value
        return record

    mutations = [
        mutant(success_witnesses=KeyError),
        mutant(success_witnesses=[]),
        mutant(outcome='verified'),
        mutant(evidence_kind='deductive'),
        mutant(evidence_kind='bounded', outcome='verified'),
        mutant(verdict_source__kind='log-parser'),
        mutant(status='proved'),
    ]
    for mutation in mutations:
        require(not validator.is_valid(mutation), 'Invalid proof-evidence mutation accepted')
    context.record('proof-evidence-envelope', 'The planned record validates against schema version 2; a missing or empty '
                                              'witness list, a verified outcome for nothing run, an executed kind with '
                                              'no run, bounded evidence without bounds, a log-parser verdict without a '
                                              'log, and the retired status field all fail. Schema validity does not '
                                              'establish a proposition.', len(mutations))
