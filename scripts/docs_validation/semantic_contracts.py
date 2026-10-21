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

import json
import re

from jsonschema import Draft202012Validator

from .context import ValidationContext, require
from .contract_examples import outcome
from .grammar import parse

TASK_SOURCE = re.compile(r'^task:(.+)$')
REQUIRED_MACRO_FORMS = {
    'comb!': ('comb-macro', 'X001'),
    'verb!': ('verb-macro', 'X004'),
    'host { ... }': ('host-block', 'E001'),
    'arr!': ('arr-macro', 'X002'),
    'array!': ('array-macro', 'X003'),
}


def catalogue_names(entry: dict) -> set[str]:
    """Return catalogue names without Markdown code marks.

    Parameters
    ----------
    entry : dict
        Vocabulary entry containing a slash-separated ``name`` field.

    Returns
    -------
    set[str]
        Normalized names suitable for comparison with excluded names.

    Examples
    --------
    ``'`comb!` / `verb!`'`` yields ``{'comb!', 'verb!'}``.
    """
    names = {name.strip(' `') for name in entry['name'].split('/')}
    return {re.sub(r'^(\.[A-Za-z_]\w*)\s*\(.*\)$', r'\1', name) for name in names}


def check_excluded_names(register: dict, catalogue: list[dict]) -> None:
    """Reject a superseded name if it reappears in the catalogue.

    Parameters
    ----------
    register : dict
        Contract register with its ``excluded_names`` list.
    catalogue : list[dict]
        Current vocabulary entries.

    Raises
    ------
    AssertionError
        If an excluded name appears in the current vocabulary.

    Examples
    --------
    A catalogue containing ``cells`` fails when that name is excluded.
    """
    names = set().union(*(catalogue_names(entry) for entry in catalogue))
    for excluded in register['excluded_names']:
        require(excluded['name'] not in names, f"Excluded name {excluded['name']} appears in the catalogue")


def mutation_changes(record: dict, mutation: str, cases: dict[str, dict], grammar: dict) -> bool:
    """Check that a seeded mutation changes one recorded outcome.

    Parameters
    ----------
    record : dict
        Contract record naming examples to compare.
    mutation : str
        Seeded change to apply to the model.
    cases : dict[str, dict]
        Example and grammar corpus indexed by identifier.
    grammar : dict
        Precedence document used by grammar examples.

    Returns
    -------
    bool
        Whether any selected example differs under the mutation.

    Examples
    --------
    Floor division changes the recorded outcome of ``idiv(-7, 2)``.
    """
    changed = False
    for example in record['examples']:
        if example.startswith('G'):
            source = cases[example]['source']
            changed |= parse(source, grammar, frozenset({mutation})) != parse(source, grammar)
        else:
            changed |= outcome(cases[example], frozenset({mutation})) != outcome(cases[example])
    return changed


def check_record(record: dict, context: dict) -> None:
    """Check one record's decisions, links, examples, mutations, and proof targets.

    Parameters
    ----------
    record : dict
        Semantic contract record under validation.
    context : dict
        Resolved decisions, catalogue, examples, errors, tasks, and components.

    Raises
    ------
    AssertionError
        If any referenced artefact is missing or violates the record.

    Examples
    --------
    An unknown catalogue identifier is rejected with the contract ID.
    """
    rid = record['id']
    decision = context['decisions'].get(record['decision'])
    require(decision is not None and decision['lifecycle'] == 'accepted', f'{rid} cites a decision that is not accepted')
    for catalogue_id in record['catalogue_ids']:
        entry = context['catalogue'].get(catalogue_id)
        require(entry is not None, f'{rid} cites unknown catalogue entry {catalogue_id}')
        require(rid in entry['contract'], f'Catalogue entry {catalogue_id} must cite {rid} in its contract')
    for relation in record['error_relation']:
        require(relation['error'] in context['error_codes'], f"{rid} uses unregistered error {relation['error']}")
    if rid == 'SC-01':
        require(any(relation['error'] == 'EmptyReduction'
                    and 'reduce' in relation['condition'] and 'fold_left' in relation['condition']
                    for relation in record['error_relation']),
                'SC-01 must register EmptyReduction for empty reduce and fold_left lanes')
    if rid == 'SC-04':
        required_catalogue_ids = {'V001', 'V002', 'V003', 'V031'}
        require(required_catalogue_ids <= set(record['catalogue_ids']),
                'SC-04 must cite add, sub, mul, and cast catalogue entries')
    if rid == 'SC-08':
        require(any(relation['error'] == 'AxisOutOfRange' and 'negative' in relation['condition'].lower()
                    for relation in record['error_relation']),
                'SC-08 must register rejection of negative axes')
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
    """Validate contract records against their schema and cited artefacts.

    Parameters
    ----------
    context : ValidationContext
        Repository root and cached JSON documents for this validation run.

    Raises
    ------
    AssertionError
        If contract links or executable witnesses disagree.
    jsonschema.ValidationError
        If a record violates the Draft 2020-12 schema.

    Examples
    --------
    An unregistered error code fails validation before evidence is recorded.
    """
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
    """Read ADR-0007 precedence rows strongest first.

    Parameters
    ----------
    text : str
        Full ADR-0007 Markdown source.

    Returns
    -------
    list[tuple[list[str], str]]
        Operator groups paired with their associativity.

    Examples
    --------
    The first returned row contains the strongest operator level.
    """
    section = text.split('## Operator precedence', 1)[1].split('\n## ', 1)[0]
    rows = [re.split(r'(?<!\\)\|', line)[1:-1] for line in section.splitlines() if line.startswith('|') and '`' in line]
    return [([op.replace('\\|', '|') for op in re.findall(r'`([^`]+)`', cells[1])], cells[2].strip().lower())
            for cells in rows]


def check_macro_grammar(context: ValidationContext) -> None:
    """Validate grammar forms, examples, coverage, and ADR agreement.

    Parameters
    ----------
    context : ValidationContext
        Repository root and cached specification documents.

    Raises
    ------
    AssertionError
        If a corpus parse, rule-coverage, production, or precedence check fails.

    Examples
    --------
    Removing the pipeline-argument witness fails the grammar coverage check.
    """
    grammar = context.load('spec/macro-grammar.json')
    forms = {form['name']: (form['production'], form['catalogue_id']) for form in grammar['forms']}
    require(len(forms) == len(grammar['forms']), 'Macro grammar form names must be unique')
    require(forms == REQUIRED_MACRO_FORMS,
            'Macro grammar must register comb!, verb!, host, arr!, and array! with their catalogue entries')
    for entry in grammar['corpus']:
        expected = entry['tree'] if entry['expect'] == 'accept' else entry['rule']
        actual = parse(entry['source'], grammar)
        require(getattr(actual, 'tree', getattr(actual, 'rule', None)) == expected,
                f"Grammar corpus {entry['id']} expected {expected}, got {actual}")
    covered = {tag for entry in grammar['corpus'] for tag in entry['covers']}
    required = ({level['name'] for level in grammar['precedence']}
                | {rule['rule'] for rule in grammar['rejections']} | {'pipeline-argument'})
    require(required <= covered, f"Grammar corpus misses {', '.join(sorted(required - covered))}")
    adr = (context.root / 'docs/adrs/adr-0007-comb-macro-grammar-and-staging.md').read_text(encoding='utf-8')
    grammar_section = adr.split('```plaintext', 1)[1].split('```', 1)[0]
    productions = {}
    for line in grammar_section.splitlines():
        if '=' in line:
            name, expression = line.split('=', 1)
            productions[name.strip()] = expression.strip().removesuffix(';').strip()
    required_forms = {form['production'] for form in grammar['forms']}
    missing_productions = required_forms - set(productions)
    require(not missing_productions,
            f"ADR-0007 grammar misses productions: {', '.join(sorted(missing_productions))}")
    array_form = next(form for form in grammar['forms'] if form['name'] == 'array!')
    array_example = array_form.get('example')
    catalogue = {entry['id']: entry for entry in context.load('spec/vocabulary.json')['entries']}
    require(isinstance(array_example, str) and array_example in catalogue['X003']['contract'],
            'array! grammar example must appear in catalogue entry X003')
    try:
        array_literal = json.loads(array_example.removeprefix('array!'))
    except json.JSONDecodeError as error:
        raise AssertionError('array! grammar example must be a nested literal array') from error
    require(array_literal == [[1, 2], [3, 4]],
            'array! grammar example must be the published nested literal array')
    expected_array_rules = {
        'array-macro': '"array!" , array-literal',
        'array-literal': '"[" , [array-element , { "," , array-element }] , "]"',
        'array-element': 'rust-expression | array-literal',
    }
    require(all(productions.get(rule) == expected for rule, expected in expected_array_rules.items()),
            'ADR-0007 array productions do not derive the published array! example')
    semantic_contracts = context.load('spec/semantic-contracts.json')['contracts']
    sc10 = next(record for record in semantic_contracts if record['id'] == 'SC-10')
    form_catalogue_ids = {catalogue_id for _, catalogue_id in forms.values()}
    require(form_catalogue_ids <= set(sc10['catalogue_ids']),
            'SC-10 must cite every macro-form catalogue entry')
    table = [(level['operators'], level['associativity']) for level in grammar['precedence']]
    require(adr_precedence(adr) == table, 'spec/macro-grammar.json disagrees with the ADR-0007 precedence table')
    context.record('macro-grammar', 'The comb! corpus parses as recorded in the documentation model, covers every '
                                    'precedence level and rejection rule plus pipeline call arguments, and agrees '
                                    'with ADR-0007. The published array! literal also derives from the recorded '
                                    'productions. Task 2.3.1 replays the corpus through trybuild.', len(grammar['corpus']))
