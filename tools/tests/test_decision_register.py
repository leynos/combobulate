"""Prove the decision register checks reject each seeded fault for its own reason."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonschema import ValidationError

from docs_validation.context import ValidationContext
from docs_validation.decisions import (
    GOVERNING_DOCUMENTS, check_adr_files, check_adr_links, check_decision_register,
    check_governing_documents, check_register_records, normalize, validate_register,
)
from docs_validation.ledger import check_generated_documents

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = ValidationContext(ROOT)
REGISTER = CONTEXT.load('spec/decisions.json')
SCHEMA = CONTEXT.load('spec/decision-register.schema.json')
ADR_PATH = 'docs/adrs/adr-0003-initial-release-scope.md'
ACCEPTED_ADR = f'# Architectural decision record (ADR) 0003: Initial release scope\n\n## Status\n\nAccepted.\n'
RETIRED = 'The classes remain proposed pending ToR Q4.'
REGISTER_LINK = 'See the [decision register](decision-register.md).\n'


def record(register: dict, decision_id: str) -> dict:
    """Return the mutable record for one decision."""
    return next(entry for entry in register['decisions'] if entry['id'] == decision_id)


def accept(register: dict, decision_id: str) -> None:
    """Accept one decision in place through a session answer by the sponsor."""
    record(register, decision_id).update({
        'lifecycle': 'accepted', 'decided_option': record(register, decision_id)['recommendation'],
        'accepted_by': 'leynos', 'accepted_on': '2026-10-10',
        'approval_reference': {'kind': 'session', 'url': 'https://example.org/session', 'author_login': 'leynos',
                               'names_decisions': [decision_id], 'answer': 'Accepted'},
    })


def accepted_register() -> dict:
    """Return a register in which D01 and D03 are accepted, D03 with its ADR and a retired statement."""
    register = copy.deepcopy(REGISTER)
    register['authorities'] = {'decision': 'D01', 'roles': {'sponsor': 'leynos', 'technical-owner': 'leynos'}}
    accept(register, 'D01')
    accept(register, 'D03')
    record(register, 'D03').update({'adr': ADR_PATH, 'retired_statements': [
        {'document': 'docs/technical-design.md', 'text': RETIRED}]})
    return register


def governing_documents() -> dict[str, str]:
    """Return minimal governing documents consistent with an accepted D03."""
    documents = {name: f'# {name}\n\n{REGISTER_LINK}' for name in GOVERNING_DOCUMENTS}
    documents['docs/terms-of-reference.md'] += (
        '\n| ID | Question | Authority |\n| --- | --- | --- |\n'
        '| Q1 | Who decides? | Accepted: [D01](decision-register.md#d01). |\n'
        '| Q4 | Is the split the release boundary? | Accepted: [D03](decision-register.md#d03). |\n'
        '| Q8 | Who accepts exceptions? | Accepted: [D01](decision-register.md#d01). |\n')
    return documents


class RegisterInvariants(unittest.TestCase):
    """VO-5: each in-register invariant has a negative control with its own message."""

    def assert_rejected(self, register: dict, message: str) -> None:
        with self.assertRaisesRegex(AssertionError, message):
            check_register_records(register)

    def test_committed_register_passes(self):
        validate_register(REGISTER, SCHEMA)
        check_register_records(REGISTER)

    def test_accepted_register_passes(self):
        register = accepted_register()
        validate_register(register, SCHEMA)
        check_register_records(register)

    def test_duplicate_identifier_fails(self):
        register = copy.deepcopy(REGISTER)
        register['decisions'].append(copy.deepcopy(record(register, 'D03')))
        self.assert_rejected(register, 'Duplicate decision D03')

    def test_unknown_recommendation_fails(self):
        register = copy.deepcopy(REGISTER)
        record(register, 'D03')['recommendation'] = 'Z'
        self.assert_rejected(register, 'Unknown recommended option in D03')

    def test_unknown_decided_option_fails(self):
        register = accepted_register()
        record(register, 'D03')['decided_option'] = 'Z'
        self.assert_rejected(register, 'Unknown decided option in D03')

    def test_approval_must_name_the_record(self):
        register = accepted_register()
        record(register, 'D03')['approval_reference']['names_decisions'] = ['D04']
        self.assert_rejected(register, 'Approval does not name D03')

    def test_approval_author_must_be_the_accepting_login(self):
        register = accepted_register()
        record(register, 'D03')['approval_reference']['author_login'] = 'someone-else'
        self.assert_rejected(register, 'Approval author differs from accepting login in D03')

    def test_acceptance_outside_the_authority_fails(self):
        register = accepted_register()
        record(register, 'D03')['accepted_by'] = 'someone-else'
        record(register, 'D03')['approval_reference']['author_login'] = 'someone-else'
        self.assert_rejected(register, 'D03 accepted by a login outside its authority')

    def test_acceptance_without_authorities_fails(self):
        register = accepted_register()
        del register['authorities']
        self.assert_rejected(register, 'D01 is accepted but the register names no authorities')

    def test_authorities_must_cite_an_accepted_decision(self):
        register = copy.deepcopy(REGISTER)
        register['authorities'] = {'decision': 'D01', 'roles': {'sponsor': 'leynos', 'technical-owner': 'leynos'}}
        self.assert_rejected(register, 'Authorities cite D01, which is not an accepted decision')

    def test_two_accepted_records_cannot_share_a_subject(self):
        register = accepted_register()
        accept(register, 'D04')
        record(register, 'D04')['subject'] = 'Initial  release scope'
        self.assert_rejected(register, 'Accepted decisions D03 and D04 share a subject')

    def test_every_in_scope_question_needs_a_live_record(self):
        register = copy.deepcopy(REGISTER)
        record(register, 'D03')['lifecycle'] = 'withdrawn'
        self.assert_rejected(register, 'In-scope questions without a live decision: Q4')

    def test_one_way_supersession_fails(self):
        register = copy.deepcopy(REGISTER)
        record(register, 'D04')['supersedes'] = ['D03']
        self.assert_rejected(register, 'One-way supersession D04 -> D03')

    def test_supersession_cycle_fails(self):
        register = copy.deepcopy(REGISTER)
        for older, newer in (('D03', 'D04'), ('D04', 'D03')):
            record(register, older)['superseded_by'] = newer
            record(register, newer)['supersedes'] = [older]
        self.assert_rejected(register, 'Supersession cycle through D03')

    def test_candidate_must_cite_a_known_decision(self):
        register = copy.deepcopy(REGISTER)
        register['candidate_adrs'][0]['decision'] = 'D99'
        self.assert_rejected(register, 'CA1 cites unknown D99')


class RegisterSchema(unittest.TestCase):
    """The schema enforces lifecycle-dependent fields and real calendar dates."""

    def test_proposed_record_cannot_carry_an_approval(self):
        register = accepted_register()
        record(register, 'D03')['lifecycle'] = 'proposed'
        with self.assertRaises(ValidationError):
            validate_register(register, SCHEMA)

    def test_accepted_record_needs_an_approval(self):
        register = accepted_register()
        record(register, 'D03')['approval_reference'] = None
        with self.assertRaises(ValidationError):
            validate_register(register, SCHEMA)

    def test_session_approval_needs_the_verbatim_answer(self):
        register = accepted_register()
        del record(register, 'D03')['approval_reference']['answer']
        with self.assertRaises(ValidationError):
            validate_register(register, SCHEMA)

    def test_impossible_date_fails(self):
        register = accepted_register()
        record(register, 'D03')['accepted_on'] = '2026-02-30'
        with self.assertRaises(ValidationError):
            validate_register(register, SCHEMA)


class AdrAgreement(unittest.TestCase):
    """Cited ADRs exist, follow the naming convention, and agree on status."""

    def setUp(self):
        self.records = check_register_records(accepted_register())

    def test_cited_adr_with_agreeing_status_passes(self):
        check_adr_files({ADR_PATH: ACCEPTED_ADR})
        check_adr_links(self.records, {ADR_PATH: ACCEPTED_ADR})

    def test_missing_adr_fails(self):
        with self.assertRaisesRegex(AssertionError, f'D03 cites missing ADR {ADR_PATH}'):
            check_adr_links(self.records, {})

    def test_status_disagreement_fails(self):
        with self.assertRaisesRegex(AssertionError, 'D03 is accepted but .* says Proposed'):
            check_adr_links(self.records, {ADR_PATH: ACCEPTED_ADR.replace('Accepted.', 'Proposed.')})

    def test_old_naming_convention_fails(self):
        with self.assertRaisesRegex(AssertionError, 'adr-nnnn-title-slug.md convention'):
            check_adr_files({'docs/adrs/adr-003-initial-release-scope.md': ACCEPTED_ADR})

    def test_title_number_must_match_the_file_name(self):
        with self.assertRaisesRegex(AssertionError, 'ADR title must start with'):
            check_adr_files({'docs/adrs/adr-0004-initial-release-scope.md': ACCEPTED_ADR})


class GoverningDocuments(unittest.TestCase):
    """VO-6: governing documents link the register and cannot contradict an accepted decision."""

    def setUp(self):
        self.records = check_register_records(accepted_register())
        self.documents = governing_documents()

    def assert_rejected(self, message: str) -> None:
        with self.assertRaisesRegex(AssertionError, message):
            check_governing_documents(self.records, self.documents)

    def test_consistent_documents_pass(self):
        check_governing_documents(self.records, self.documents)

    def test_missing_register_link_fails(self):
        self.documents['docs/context.md'] = '# Context\n'
        self.assert_rejected('docs/context.md must link the decision register')

    def test_reinserted_retired_statement_fails(self):
        self.documents['docs/technical-design.md'] += f'\n{RETIRED}\n'
        self.assert_rejected('still states text retired by D03')

    def test_rewrapped_retired_statement_fails(self):
        self.documents['docs/technical-design.md'] += '\nThe classes remain *proposed*\npending ToR Q4.\n'
        self.assert_rejected('still states text retired by D03')

    def test_open_status_wording_fails(self):
        self.documents['docs/roadmap.md'] += '\nScope question Q4 remains open.\n'
        self.assert_rejected(r"docs/roadmap.md describes Q4 \(D03\) as 'remains open'|as 'open'")

    def test_missing_terms_of_reference_anchor_fails(self):
        terms = self.documents['docs/terms-of-reference.md']
        self.documents['docs/terms-of-reference.md'] = terms.replace('decision-register.md#d03', 'decision-register.md')
        self.assert_rejected('ToR §9 row Q4 must link decision-register.md#d03')

    def test_normalization_strips_inline_markdown(self):
        self.assertEqual(normalize('*Q4* `remains`\n [open](x.md)'), 'Q4 remains open',
                         'normalization must strip emphasis, code, links, and wrapping')


class RealRegister(unittest.TestCase):
    """The committed register, ADRs, and governing documents pass, and hand edits are caught (VO-14)."""

    def test_committed_register_passes_the_checker(self):
        check_decision_register(ValidationContext(ROOT))

    def test_hand_edited_register_document_fails_the_drift_check(self):
        context = ValidationContext(ROOT)
        text = (ROOT / 'docs/decision-register.md').read_text(encoding='utf-8')
        edited = text.replace('Decision: pending.', 'Decision: option A.', 1)
        original = Path.read_text

        def read_text(path: Path, *args, **kwargs) -> str:
            return edited if path == ROOT / 'docs/decision-register.md' else original(path, *args, **kwargs)

        with patch.object(Path, 'read_text', read_text):
            with self.assertRaisesRegex(AssertionError, 'Generated content drift: docs/decision-register.md'):
                check_generated_documents(context, context.load('spec/vocabulary.json')['entries'])


if __name__ == '__main__':
    unittest.main()
