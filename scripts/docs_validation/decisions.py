"""Validate the decision register and its agreement with the governing documents.

`spec/decisions.json` is the master for `docs/decision-register.md`. These
checks keep accepted decisions attributable (an accepting login named by the
D01 authority, a structured approval reference naming the record), keep the
lifecycle honest (proposed records carry no approval, supersession is two-way
and acyclic, a cited ADR agrees on status), and keep the five governing
documents from contradicting an accepted decision. Each pure check accepts
in-memory data so tests can seed one fault at a time.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from jsonschema import Draft202012Validator

from .adr_naming import ADR_NAME, canonical_adr_path
from .context import ValidationContext, require

GOVERNING_DOCUMENTS = (
    'docs/terms-of-reference.md', 'docs/context.md', 'docs/technical-design.md',
    'docs/language-reference.md', 'docs/roadmap.md',
)
REGISTER_LINK = re.compile(r'\]\((?:\.\./docs/|\./)?decision-register\.md(?:#[^)]*)?\)')
OPEN_STATUS = re.compile(r'\b(?:pending|open|unresolved|remains? proposed)\b', re.IGNORECASE)
OPEN_STATUS_WINDOW = 60
ADR_STATUS = {'proposed': 'Proposed', 'accepted': 'Accepted', 'superseded': 'Superseded'}
KNOWN_ADR_STATUSES = frozenset(ADR_STATUS.values()) | {'Deprecated'}
LIVE = {'proposed', 'accepted'}
AUTHORITY_DECISION = 'D01'
APPROVAL_LOGIN = 'leynos'


def validate_register(register: dict, schema: dict) -> None:
    """Validate the register against its Draft 2020-12 schema, including date formats.

    For example, validate the committed register against its schema from the
    repository root::

        >>> from pathlib import Path
        >>> context = ValidationContext(Path.cwd())
        >>> validate_register(context.load('spec/decisions.json'),
        ...                   context.load('spec/decision-register.schema.json'))
    """
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(register)


def index_records(register: dict) -> dict[str, dict]:
    """Index decisions by identifier and reject duplicate IDs.

    For example, a D03 record is indexed under its identifier::

        >>> index_records({'decisions': [{'id': 'D03', 'subject': 'Example'}]})
        {'D03': {'id': 'D03', 'subject': 'Example'}}
    """
    records: dict[str, dict] = {}
    for record in register['decisions']:
        require(record['id'] not in records, f"Duplicate decision {record['id']}")
        records[record['id']] = record
    return records


def is_accepted(record: dict) -> bool:
    """Report whether a record currently binds; superseded and withdrawn records do not.

    For example, only an accepted record currently binds::

        >>> is_accepted({'lifecycle': 'accepted'})
        True
    """
    return record['lifecycle'] == 'accepted'


def check_options(record: dict) -> None:
    """Require the recommendation and any decided option to name a listed option.

    For example, a proposed record may recommend option A without deciding it::

        >>> check_options({'id': 'D01', 'options': [{'id': 'A'}],
        ...                'recommendation': 'A', 'decided_option': None})
    """
    option_ids = [option['id'] for option in record['options']]
    require(len(option_ids) == len(set(option_ids)), f"Duplicate option in {record['id']}")
    require(record['recommendation'] in option_ids, f"Unknown recommended option in {record['id']}")
    decided = record['decided_option']
    require(decided is None or decided in option_ids, f"Unknown decided option in {record['id']}")


def check_approval(record: dict, authorities: dict | None) -> None:
    """Require approval to name the decision and come from an authorised login.

    For example, a D03 approval by the sponsor passes when D01 assigns that
    role to the accepting login::

        >>> record = {'id': 'D03', 'approval_reference': {
        ...     'names_decisions': ['D03'], 'author_login': 'leynos'},
        ...     'accepted_by': 'leynos', 'authority_roles': ['sponsor']}
        >>> check_approval(record, {'roles': {'sponsor': 'leynos'}})
    """
    reference = record['approval_reference']
    if reference is None:
        return
    require(record['id'] in reference['names_decisions'], f"Approval does not name {record['id']}")
    require(reference['author_login'] == record['accepted_by'],
            f"Approval author differs from accepting login in {record['id']}")
    require(authorities is not None, f"{record['id']} is accepted but the register names no authorities")
    allowed = {authorities['roles'][role] for role in record['authority_roles']}
    require(record['accepted_by'] in allowed, f"{record['id']} accepted by a login outside its authority")
    require(record['accepted_by'] == APPROVAL_LOGIN,
            f"{record['id']} must be accepted by {APPROVAL_LOGIN}")


def check_authorities(register: dict, records: dict[str, dict]) -> None:
    """Require the authority map to cite accepted D01, the source of approval authority.

    For example, the authority map passes once D01 is accepted::

        >>> check_authorities({'authorities': {'decision': 'D01'}},
        ...                   {'D01': {'lifecycle': 'accepted'}})
    """
    authorities = register.get('authorities')
    if authorities is None:
        return
    require(authorities['decision'] == AUTHORITY_DECISION,
            f"Authorities must cite {AUTHORITY_DECISION}, not {authorities['decision']}")
    source = records.get(authorities['decision'])
    require(source is not None and is_accepted(source),
            f"Authorities cite {authorities['decision']}, which is not an accepted decision")


def check_subjects(records: dict[str, dict]) -> None:
    """Require one accepted, non-superseded record per subject.

    For example, a proposed record may use an accepted record's subject while
    the decision is still under consideration::

        >>> records = {
        ...     'D01': {'id': 'D01', 'lifecycle': 'accepted', 'subject': 'Package licence'},
        ...     'D02': {'id': 'D02', 'lifecycle': 'proposed', 'subject': 'Package licence'},
        ... }
        >>> check_subjects(records)
    """
    subjects: dict[str, str] = {}
    for record in records.values():
        if not is_accepted(record):
            continue
        subject = ' '.join(record['subject'].lower().split())
        require(subject not in subjects, f"Accepted decisions {subjects.get(subject)} and {record['id']} share a subject")
        subjects[subject] = record['id']


def check_questions(register: dict, records: dict[str, dict]) -> None:
    """Require every in-scope ToR question to have a live decision record.

    For example, a proposed D01 can cover Q1 while it remains an experiment::

        >>> check_questions({'in_scope_questions': ['Q1']}, {'D01': {
        ...     'lifecycle': 'proposed', 'questions': ['Q1']}})
    """
    covered = {question for record in records.values() if record['lifecycle'] in LIVE
               for question in record['questions']}
    missing = sorted(set(register['in_scope_questions']) - covered)
    require(not missing, f"In-scope questions without a live decision: {', '.join(missing)}")


def check_supersession(records: dict[str, dict]) -> None:
    """Require linked, acyclic supersession chains to end at an accepted decision.

    For example, D02 may supersede D01 when both records name the relationship::

        >>> records = {
        ...     'D01': {'id': 'D01', 'supersedes': [], 'superseded_by': 'D02',
        ...             'lifecycle': 'superseded'},
        ...     'D02': {'id': 'D02', 'supersedes': ['D01'], 'superseded_by': None,
        ...             'lifecycle': 'accepted'}}
        >>> check_supersession(records)
    """
    for record in records.values():
        for older in record['supersedes']:
            require(older in records, f"{record['id']} supersedes unknown {older}")
            require(records[older]['superseded_by'] == record['id'], f"One-way supersession {record['id']} -> {older}")
        newer = record['superseded_by']
        if newer is not None:
            require(newer in records, f"{record['id']} superseded by unknown {newer}")
            require(record['id'] in records[newer]['supersedes'], f"One-way supersession {newer} -> {record['id']}")
            require(records[newer]['lifecycle'] in {'accepted', 'superseded'},
                    f"{newer} must be accepted before superseding {record['id']}")
    for record in records.values():
        seen = {record['id']}
        current = record
        while current['superseded_by'] is not None:
            current = records[current['superseded_by']]
            require(current['id'] not in seen, f"Supersession cycle through {record['id']}")
            seen.add(current['id'])


def check_candidates(register: dict, records: dict[str, dict]) -> None:
    """Require unique candidate ADR subjects whose disposition decision exists.

    For example, a schema-shaped candidate CA1 passes when D03 records its
    disposition::

        >>> candidate = {'id': 'CA1', 'subject': 'Archive format',
        ...              'source': 'technical-design.md §15', 'decision': 'D03',
        ...              'disposition': {'kind': 'adr', 'adrs': ['ADR-0001']}}
        >>> check_candidates({'candidate_adrs': [candidate]}, {'D03': {}})
    """
    ids = [candidate['id'] for candidate in register['candidate_adrs']]
    require(len(ids) == len(set(ids)), 'Duplicate candidate ADR subject')
    for candidate in register['candidate_adrs']:
        require(candidate['decision'] in records, f"{candidate['id']} cites unknown {candidate['decision']}")


def check_register_records(register: dict) -> dict[str, dict]:
    """Run every in-register invariant (VO-5) and return the indexed records.

    For example, the committed register returns one indexed record per
    decision::

        >>> from pathlib import Path
        >>> context = ValidationContext(Path.cwd())
        >>> register = context.load('spec/decisions.json')
        >>> len(check_register_records(register)) == len(register['decisions'])
        True
    """
    records = index_records(register)
    check_authorities(register, records)
    for record in records.values():
        check_options(record)
        check_approval(record, register.get('authorities'))
    check_subjects(records)
    check_questions(register, records)
    check_supersession(records)
    check_candidates(register, records)
    return records


def adr_status(text: str) -> str:
    """Return the first word of an ADR's Status section; e.g. 'Accepted on 2026-10-10' gives 'Accepted'."""
    match = re.search(r'^## Status\s*\n\s*\n?([A-Za-z]+)', text, re.MULTILINE)
    return match.group(1) if match else ''


def check_adr_files(adrs: Mapping[str, str]) -> None:
    """Require each ADR filename to be the canonical name its own title implies.

    For example, a numbered ADR with a known status passes::

        >>> check_adr_files({'docs/adrs/adr-0001-repository-bootstrap.md':
        ...     '# Architectural decision record (ADR) 0001: Repository bootstrap\\n\\n'
        ...     '## Status\\n\\nProposed.\\n'})

    The number and the slug must both come from that title, so a file whose
    name disagrees with the document it contains is rejected even when only
    the slug differs.
    """
    for path, text in adrs.items():
        require(ADR_NAME.match(path) is not None, f'ADR name breaks the adr-nnnn-title-slug.md convention: {path}')
        expected = canonical_adr_path(text)
        require(expected is not None,
                f'ADR title must start with a numbered "# Architectural decision record (ADR) nnnn: " heading: {path}')
        require(path == expected, f'ADR {path} must be named {expected} to match its title')
        require(adr_status(text) in KNOWN_ADR_STATUSES, f'ADR lacks a known Status: {path}')


def check_adr_links(records: dict[str, dict], adrs: Mapping[str, str]) -> None:
    """Require each cited ADR to exist and agree with its decision's lifecycle.

    For example, a proposed decision may cite a proposed ADR::

        >>> path = 'docs/adrs/adr-0001-repository-bootstrap.md'
        >>> adr = '# Architectural decision record (ADR) 0001: Repository bootstrap\\n\\n'
        >>> adr += '## Status\\n\\nProposed.\\n'
        >>> check_adr_links({'D01': {'id': 'D01', 'lifecycle': 'proposed', 'adr': path}},
        ...                 {path: adr})
    """
    for record in records.values():
        path = record['adr']
        if path is None:
            continue
        require(path in adrs, f"{record['id']} cites missing ADR {path}")
        expected = ADR_STATUS.get(record['lifecycle'])
        require(expected is None or adr_status(adrs[path]) == expected,
                f"{record['id']} is {record['lifecycle']} but {path} says {adr_status(adrs[path])}")


def normalize(text: str) -> str:
    """Strip inline Markdown and collapse whitespace; e.g. '*Q4* `remains`\\n open' gives 'Q4 remains open'."""
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'[*_`]', '', text)
    return ' '.join(text.split())


def accepted_questions(records: dict[str, dict]) -> dict[str, list[str]]:
    """Map each question to the accepted decisions that answer it.

    For example, accepted D01 is recorded as the answer to Q1::

        >>> accepted_questions({'D01': {'id': 'D01', 'lifecycle': 'accepted',
        ...                             'questions': ['Q1']}})
        {'Q1': ['D01']}
    """
    answered: dict[str, list[str]] = {}
    for record in records.values():
        if is_accepted(record):
            for question in record['questions']:
                answered.setdefault(question, []).append(record['id'])
    return answered


def check_question_anchor(terms: str, question: str, decision_ids: list[str]) -> None:
    """Require the ToR §9 row for an accepted question to link one of its register anchors.

    For example, Q1 passes when its row links the D01 register heading::

        >>> check_question_anchor('| Q1 | Who decides? | [D01](decision-register.md#d01) |',
        ...                      'Q1', ['D01'])
    """
    row = next((line for line in terms.splitlines() if re.match(rf'^\|\s*{question}\s*\|', line)), None)
    require(row is not None, f'Terms of reference §9 has no row for {question}')
    anchors = {f'decision-register.md#{decision.lower()}' for decision in decision_ids}
    require(any(anchor in row for anchor in anchors),
            f"ToR §9 row {question} must link {' or '.join(sorted(anchors))}")


def check_open_status(name: str, text: str, question: str, decision_ids: list[str]) -> None:
    """Reject open-status wording near an accepted question's identifier.

    For example, an accepted Q1 may be described without pending wording::

        >>> check_open_status('docs/context.md', 'Q1 is accepted.', 'Q1', ['D01'])
    """
    for match in re.finditer(rf'\b{question}\b', text):
        window = text[max(0, match.start() - OPEN_STATUS_WINDOW):match.end() + OPEN_STATUS_WINDOW]
        found = OPEN_STATUS.search(window)
        require(found is None, f"{name} describes {question} ({', '.join(decision_ids)}) as "
                               f"{found.group(0) if found else ''!r}: {window!r}")


def check_governing_documents(records: dict[str, dict], documents: Mapping[str, str]) -> None:
    """Keep the five governing documents linked to and consistent with accepted decisions (VO-6).

    For example, the required register link in each document is enough when
    there are no accepted decisions yet::

        >>> documents = {name: '[Decision register](decision-register.md)'
        ...              for name in GOVERNING_DOCUMENTS}
        >>> check_governing_documents({}, documents)
    """
    normalized = {name: normalize(text) for name, text in documents.items()}
    for name, text in documents.items():
        require(REGISTER_LINK.search(text) is not None, f'{name} must link the decision register')
    for record in records.values():
        if not is_accepted(record):
            continue
        for statement in record['retired_statements']:
            require(normalize(statement['text']) not in normalized[statement['document']],
                    f"{statement['document']} still states text retired by {record['id']}: {statement['text']!r}")
    for question, decision_ids in accepted_questions(records).items():
        check_question_anchor(documents['docs/terms-of-reference.md'], question, decision_ids)
        for name, text in normalized.items():
            check_open_status(name, text, question, decision_ids)


def check_decision_register(context: ValidationContext) -> None:
    """Validate the register master, ADRs, and governing documents together.

    From the repository root, a passing run records the number of decisions checked::

        >>> from pathlib import Path
        >>> context = ValidationContext(Path.cwd())
        >>> check_decision_register(context)
        >>> context.results[0]['check']
        'decision-register'
    """
    register = context.load('spec/decisions.json')
    validate_register(register, context.load('spec/decision-register.schema.json'))
    records = check_register_records(register)
    adrs = {path.relative_to(context.root).as_posix(): path.read_text(encoding='utf-8')
            for path in sorted((context.root / 'docs/adrs').glob('*.md'))}
    check_adr_files(adrs)
    check_adr_links(records, adrs)
    documents = {name: (context.root / name).read_text(encoding='utf-8') for name in GOVERNING_DOCUMENTS}
    check_governing_documents(records, documents)
    accepted = sum(is_accepted(record) for record in records.values())
    context.record('decision-register',
                   f'Schema, identities, options, approvals, supersession, ADR status agreement, and governing-document '
                   f'links pass; {accepted} of {len(records)} decisions are accepted. Acceptance is not verification.',
                   len(records))
