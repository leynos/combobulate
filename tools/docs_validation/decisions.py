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

from .context import ValidationContext, require

GOVERNING_DOCUMENTS = (
    'docs/terms-of-reference.md', 'docs/context.md', 'docs/technical-design.md',
    'docs/language-reference.md', 'docs/roadmap.md',
)
REGISTER_LINK = re.compile(r'\]\((?:\.\./docs/|\./)?decision-register\.md(?:#[^)]*)?\)')
OPEN_STATUS = re.compile(r'\b(?:pending|open|unresolved|remains? proposed)\b', re.IGNORECASE)
OPEN_STATUS_WINDOW = 60
ADR_NAME = re.compile(r'^docs/adrs/adr-(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$')
ADR_STATUS = {'proposed': 'Proposed', 'accepted': 'Accepted', 'superseded': 'Superseded'}
KNOWN_ADR_STATUSES = frozenset(ADR_STATUS.values()) | {'Deprecated'}
LIVE = {'proposed', 'accepted'}


def validate_register(register: dict, schema: dict) -> None:
    """Validate the register against its Draft 2020-12 schema, including date formats."""
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(register)


def index_records(register: dict) -> dict[str, dict]:
    """Index decisions by identifier; e.g. two records named D03 fail."""
    records: dict[str, dict] = {}
    for record in register['decisions']:
        require(record['id'] not in records, f"Duplicate decision {record['id']}")
        records[record['id']] = record
    return records


def is_accepted(record: dict) -> bool:
    """Report whether a record currently binds; superseded and withdrawn records do not."""
    return record['lifecycle'] == 'accepted'


def check_options(record: dict) -> None:
    """Require the recommendation and any decided option to name a listed option."""
    option_ids = [option['id'] for option in record['options']]
    require(len(option_ids) == len(set(option_ids)), f"Duplicate option in {record['id']}")
    require(record['recommendation'] in option_ids, f"Unknown recommended option in {record['id']}")
    decided = record['decided_option']
    require(decided is None or decided in option_ids, f"Unknown decided option in {record['id']}")


def check_approval(record: dict, authorities: dict | None) -> None:
    """Require an accepted record's approval to come from its authority and to name it."""
    reference = record['approval_reference']
    if reference is None:
        return
    require(record['id'] in reference['names_decisions'], f"Approval does not name {record['id']}")
    require(reference['author_login'] == record['accepted_by'],
            f"Approval author differs from accepting login in {record['id']}")
    require(authorities is not None, f"{record['id']} is accepted but the register names no authorities")
    allowed = {authorities['roles'][role] for role in record['authority_roles']}
    require(record['accepted_by'] in allowed, f"{record['id']} accepted by a login outside its authority")


def check_authorities(register: dict, records: dict[str, dict]) -> None:
    """Require the authority map to come from an accepted decision once anything is accepted."""
    authorities = register.get('authorities')
    if authorities is None:
        return
    source = records.get(authorities['decision'])
    require(source is not None and is_accepted(source),
            f"Authorities cite {authorities['decision']}, which is not an accepted decision")


def check_subjects(records: dict[str, dict]) -> None:
    """Require one accepted, non-superseded record per subject; e.g. two accepted 'Package licence' fail."""
    subjects: dict[str, str] = {}
    for record in records.values():
        if not is_accepted(record):
            continue
        subject = ' '.join(record['subject'].lower().split())
        require(subject not in subjects, f"Accepted decisions {subjects.get(subject)} and {record['id']} share a subject")
        subjects[subject] = record['id']


def check_questions(register: dict, records: dict[str, dict]) -> None:
    """Require every in-scope ToR question to be covered by a live (proposed or accepted) record."""
    covered = {question for record in records.values() if record['lifecycle'] in LIVE
               for question in record['questions']}
    missing = sorted(set(register['in_scope_questions']) - covered)
    require(not missing, f"In-scope questions without a live decision: {', '.join(missing)}")


def check_supersession(records: dict[str, dict]) -> None:
    """Require two-way, acyclic supersession links; a one-way or circular link fails."""
    for record in records.values():
        for older in record['supersedes']:
            require(older in records, f"{record['id']} supersedes unknown {older}")
            require(records[older]['superseded_by'] == record['id'], f"One-way supersession {record['id']} -> {older}")
        newer = record['superseded_by']
        if newer is not None:
            require(newer in records, f"{record['id']} superseded by unknown {newer}")
            require(record['id'] in records[newer]['supersedes'], f"One-way supersession {newer} -> {record['id']}")
    for record in records.values():
        seen = {record['id']}
        current = record
        while current['superseded_by'] is not None:
            current = records[current['superseded_by']]
            require(current['id'] not in seen, f"Supersession cycle through {record['id']}")
            seen.add(current['id'])


def check_candidates(register: dict, records: dict[str, dict]) -> None:
    """Require unique candidate ADR subjects whose disposition decision exists."""
    ids = [candidate['id'] for candidate in register['candidate_adrs']]
    require(len(ids) == len(set(ids)), 'Duplicate candidate ADR subject')
    for candidate in register['candidate_adrs']:
        require(candidate['decision'] in records, f"{candidate['id']} cites unknown {candidate['decision']}")


def check_register_records(register: dict) -> dict[str, dict]:
    """Run every in-register invariant (VO-5) and return the indexed records."""
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
    """Require ADR names and titles to follow the docs/adrs convention with matching numbers."""
    for path, text in adrs.items():
        match = ADR_NAME.match(path)
        require(match is not None, f'ADR name breaks the adr-nnnn-title-slug.md convention: {path}')
        title = f'# Architectural decision record (ADR) {match.group(1)}: '
        require(text.startswith(title), f'ADR title must start with {title!r}: {path}')
        require(adr_status(text) in KNOWN_ADR_STATUSES, f'ADR lacks a known Status: {path}')


def check_adr_links(records: dict[str, dict], adrs: Mapping[str, str]) -> None:
    """Require each cited ADR to exist and to agree with its decision's lifecycle."""
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
    """Map each question to the accepted decisions that answer it."""
    answered: dict[str, list[str]] = {}
    for record in records.values():
        if is_accepted(record):
            for question in record['questions']:
                answered.setdefault(question, []).append(record['id'])
    return answered


def check_question_anchor(terms: str, question: str, decision_ids: list[str]) -> None:
    """Require the ToR §9 row for an accepted question to link one of its register anchors."""
    row = next((line for line in terms.splitlines() if re.match(rf'^\|\s*{question}\s*\|', line)), None)
    require(row is not None, f'Terms of reference §9 has no row for {question}')
    anchors = {f'decision-register.md#{decision.lower()}' for decision in decision_ids}
    require(any(anchor in row for anchor in anchors),
            f"ToR §9 row {question} must link {' or '.join(sorted(anchors))}")


def check_open_status(name: str, text: str, question: str, decision_ids: list[str]) -> None:
    """Reject open-status wording within the window around an accepted question's identifier."""
    for match in re.finditer(rf'\b{question}\b', text):
        window = text[max(0, match.start() - OPEN_STATUS_WINDOW):match.end() + OPEN_STATUS_WINDOW]
        found = OPEN_STATUS.search(window)
        require(found is None, f"{name} describes {question} ({', '.join(decision_ids)}) as "
                               f"{found.group(0) if found else ''!r}: {window!r}")


def check_governing_documents(records: dict[str, dict], documents: Mapping[str, str]) -> None:
    """Keep the five governing documents linked to, and consistent with, accepted decisions (VO-6)."""
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
    """Validate the register master, its ADRs, and the governing documents against each other."""
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
