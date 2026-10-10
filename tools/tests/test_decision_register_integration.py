"""Exercise the decision register through the composed repository checks."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_docs import collect_checks
from docs_validation.context import ValidationContext
from docs_validation.decisions import (
    GOVERNING_DOCUMENTS, check_decision_register, check_governing_documents, check_register_records,
)
from docs_validation.ledger import check_generated_documents, generated_documents
from test_decision_register import REGISTER, RETIRED

ROOT = Path(__file__).resolve().parents[2]


class RealRegister(unittest.TestCase):
    """The committed register passes, and hand edits are caught (VO-14)."""

    def test_committed_register_passes_the_checker(self) -> None:
        """Validate the committed decision register with the composed checker."""
        check_decision_register(ValidationContext(ROOT))

    def test_composed_checker_records_the_decision_register(self) -> None:
        """Include decision-register validation in the complete check sequence."""
        context = ValidationContext(ROOT)
        collect_checks(context)
        result = next(row for row in context.results if row['check'] == 'decision-register')
        self.assertEqual(result['count'], 15,
                         'the composed documentation checker validates all 15 decisions')

    def test_decision_register_generator_is_in_the_generated_document_catalogue(self) -> None:
        """Pair the rendered register with its checked-in source and generator."""
        context = ValidationContext(ROOT)
        catalogue = context.load('spec/vocabulary.json')['entries']
        register_entries = [
            (Path(generator.__file__).resolve(), source, path)
            for generator, source, path in generated_documents(context, catalogue)
            if path == 'docs/decision-register.md'
        ]
        self.assertEqual(
            register_entries,
            [(ROOT / 'scripts/generate_decisions.py', REGISTER, 'docs/decision-register.md')],
            'the generated-document check must pair the register with its master and renderer',
        )

    def test_hand_edited_register_document_fails_the_drift_check(self) -> None:
        """Reject a hand edit that changes generated register wording."""
        context = ValidationContext(ROOT)
        text = (ROOT / 'docs/decision-register.md').read_text(encoding='utf-8')
        edited = text.replace('### D01\n', '### D99\n', 1)
        self.assertNotEqual(edited, text, 'the generated decision heading must be present for mutation')
        original = Path.read_text

        def read_text(path: Path, *args: Any, **kwargs: Any) -> str:
            """Return the mutated register text only for the generated document."""
            return edited if path == ROOT / 'docs/decision-register.md' else original(path, *args, **kwargs)

        with patch.object(Path, 'read_text', read_text):
            with self.assertRaisesRegex(AssertionError, 'Generated content drift: docs/decision-register.md'):
                check_generated_documents(context, context.load('spec/vocabulary.json')['entries'])


class RealGoverningDocuments(unittest.TestCase):
    """Keep accepted decisions reconciled with the committed governing documents."""

    def setUp(self) -> None:
        self.records = check_register_records(REGISTER)
        self.documents = {name: (ROOT / name).read_text(encoding='utf-8') for name in GOVERNING_DOCUMENTS}

    def assert_rejected(self, message: str) -> None:
        with self.assertRaisesRegex(AssertionError, message):
            check_governing_documents(self.records, self.documents)

    def test_committed_documents_pass(self) -> None:
        """The five committed governing documents satisfy accepted decisions."""
        check_governing_documents(self.records, self.documents)

    def test_reinserted_q4_sentence_names_d03(self) -> None:
        """Reject a retired release-scope sentence with its decision identifier."""
        self.documents['docs/technical-design.md'] += f'\n{RETIRED}\n'
        self.assert_rejected('still states text retired by D03')

    def test_rewrapped_q4_sentence_names_d03(self) -> None:
        """Detect the retired sentence across a Markdown line wrap."""
        self.documents['docs/technical-design.md'] += '\nThe classes remain proposed\npending ToR Q4.\n'
        self.assert_rejected('still states text retired by D03')

    def test_q4_described_as_open_names_d03(self) -> None:
        """Reject a live document that describes the accepted Q4 scope as open."""
        self.documents['docs/roadmap.md'] += '\nQ4 remains open.\n'
        self.assert_rejected(r'docs/roadmap.md describes Q4 \(D03\)')

    def test_deleted_q4_anchor_names_d03(self) -> None:
        """Require the Terms of Reference Q4 row to retain its decision anchor."""
        terms = self.documents['docs/terms-of-reference.md']
        self.documents['docs/terms-of-reference.md'] = terms.replace('decision-register.md#d03', 'decision-register.md')
        self.assert_rejected('ToR §9 row Q4 must link decision-register.md#d03')


if __name__ == '__main__':
    unittest.main()
