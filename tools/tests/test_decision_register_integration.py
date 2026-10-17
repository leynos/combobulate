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
from docs_validation.decisions import check_decision_register
from docs_validation.ledger import check_generated_documents, generated_documents
from test_decision_register import REGISTER

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


if __name__ == '__main__':
    unittest.main()
