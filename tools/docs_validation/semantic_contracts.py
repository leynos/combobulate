"""Validate semantic contract records against the catalogue, examples, and grammar corpus.

Each record in `spec/semantic-contracts.json` states one primitive's logical
contract and takes its acceptance from an accepted decision. These checks keep
records complete (VO-8): every catalogue identifier exists and its catalogue
contract cites the record; errors are registered codes; examples exist, name
the record, and evaluate as recorded; every seeded mutation changes at least
one of the record's outcomes; and the record is discharged by a real obligation
component or task. They also keep superseded names out of the catalogue (VO-10).
"""
from __future__ import annotations

import re

from jsonschema import Draft202012Validator

from .context import ValidationContext, require
from .contract_examples import outcome
from .grammar import parse

TASK_SOURCE = re.compile(r'^task:(.+)$')


def catalogue_names(entry: dict) -> set[str]:
    """Return an entry's names without Markdown code marks; e.g. '`comb!`' gives {'comb!'}."""
    return {name.strip(' `') for name in entry['name'].split('/')}


def check_excluded_names(register: dict, catalogue: list[dict]) -> None:
    """Reject a superseded name reappearing as a catalogue name (VO-10)."""
    names = set().union(*(catalogue_names(entry) for entry in catalogue))
    for excluded in register['excluded_names']:
        require(excluded['name'] not in names, f"Excluded name {excluded['name']} appears in the catalogue")


def mutation_changes(record: dict, mutation: str, cases: dict[str, dict], grammar: dict) -> bool:
    """Report whether one seeded mutation changes any of a record's example outcomes."""
    changed = False
    for example in record['examples']:
        if example.startswith('G'):
            source = cases[example]['source']
            changed |= parse(source, grammar, frozenset({mutation})) != parse(source, grammar)
        else:
            changed |= outcome(cases[example], frozenset({mutation})) != outcome(cases[example])
    return changed


def check_record(record: dict, context: dict) -> None:
    """Check one record's links, examples, mutations, and discharge targets."""
    rid = record['id']
    decision = context['decisions'].get(record['decision'])
    require(decision is not None and decision['lifecycle'] == 'accepted', f'{rid} cites a decision that is not accepted')
    for catalogue_id in record['catalogue_ids']:
        entry = context['catalogue'].get(catalogue_id)
        require(entry is not None, f'{rid} cites unknown catalogue entry {catalogue_id}')
        require(rid in entry['contract'], f'Catalogue entry {catalogue_id} must cite {rid} in its contract')
    for relation in record['error_relation']:
        require(relation['error'] in context['error_codes'], f"{rid} uses unregistered error {relation['error']}")
    for example in record['examples']:
        case = context['cases'].get(example)
        require(case is not None, f'{rid} cites unknown example {example}')
        owner = case.get('contract', rid)
        require(owner == rid, f'{example} belongs to {owner}, not {rid}')
    for mutation in record['seeded_mutations']:
        require(mutation_changes(record, mutation['id'], context['cases'], context['grammar']),
                f"Seeded mutation {mutation['id']} changes no outcome of {rid}")
    for target in record['discharged_by']:
        task = TASK_SOURCE.match(target)
        known = task.group(1) in context['tasks'] if task else target in context['components']
        require(known, f'{rid} is discharged by unknown {target}')


def check_semantic_contracts(context: ValidationContext) -> None:
    """Validate the contract register against its schema and every artefact it cites."""
    register = context.load('spec/semantic-contracts.json')
    Draft202012Validator(context.load('spec/semantic-contract.schema.json')).validate(register)
    ids = [record['id'] for record in register['contracts']]
    require(len(ids) == len(set(ids)), 'Duplicate semantic contract ID')
    catalogue = context.load('spec/vocabulary.json')['entries']
    grammar = context.load('spec/macro-grammar.json')
    examples = context.load('spec/examples.json')['contract_cases']
    obligations = context.load('spec/proof-obligations.json')['obligations']
    roadmap = context.load('spec/roadmap.json')
    links = {
        'decisions': {record['id']: record for record in context.load('spec/decisions.json')['decisions']},
        'catalogue': {entry['id']: entry for entry in catalogue},
        'cases': {case['id']: case for case in examples} | {entry['id']: entry for entry in grammar['corpus']},
        'grammar': grammar, 'error_codes': set(register['error_codes']),
        'components': {component['id'] for obligation in obligations for component in obligation['components']},
        'tasks': {task['id'] for phase in roadmap['phases'] for step in phase['steps'] for task in step['tasks']},
    }
    for record in register['contracts']:
        check_record(record, links)
    unowned = sorted({case['id'] for case in examples} - {example for record in register['contracts']
                                                           for example in record['examples']})
    require(not unowned, f"Contract examples cited by no record: {', '.join(unowned)}")
    check_excluded_names(register, catalogue)
    context.record('semantic-contracts', 'Contract records are complete, cite accepted decisions, registered errors, '
                                         'owned examples, and real discharge targets; every seeded mutation changes '
                                         'an outcome; superseded names stay out of the catalogue.', len(ids))


def adr_precedence(text: str) -> list[tuple[list[str], str]]:
    """Read the ADR-0007 precedence table rows as (operators, associativity), strongest first."""
    section = text.split('## Operator precedence', 1)[1].split('\n## ', 1)[0]
    rows = [re.split(r'(?<!\\)\|', line)[1:-1] for line in section.splitlines() if line.startswith('|') and '`' in line]
    return [([op.replace('\\|', '|') for op in re.findall(r'`([^`]+)`', cells[1])], cells[2].strip().lower())
            for cells in rows]


def check_macro_grammar(context: ValidationContext) -> None:
    """Require the corpus to parse as recorded, cover every rule, and agree with ADR-0007 (VO-9)."""
    grammar = context.load('spec/macro-grammar.json')
    for entry in grammar['corpus']:
        expected = entry['tree'] if entry['expect'] == 'accept' else entry['rule']
        actual = parse(entry['source'], grammar)
        require(getattr(actual, 'tree', getattr(actual, 'rule', None)) == expected,
                f"Grammar corpus {entry['id']} expected {expected}, got {actual}")
    covered = {tag for entry in grammar['corpus'] for tag in entry['covers']}
    required = {level['name'] for level in grammar['precedence']} | {rule['rule'] for rule in grammar['rejections']}
    require(required <= covered, f"Grammar corpus misses {', '.join(sorted(required - covered))}")
    adr = (context.root / 'docs/adrs/adr-0007-comb-macro-grammar-and-staging.md').read_text(encoding='utf-8')
    table = [(level['operators'], level['associativity']) for level in grammar['precedence']]
    require(adr_precedence(adr) == table, 'spec/macro-grammar.json disagrees with the ADR-0007 precedence table')
    context.record('macro-grammar', 'The comb! corpus parses as recorded in the documentation model, covers every '
                                    'precedence level and rejection rule, and agrees with ADR-0007. Task 2.3.1 '
                                    'replays it through trybuild.', len(grammar['corpus']))
