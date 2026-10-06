"""Reject duplicate declared identities before set-based reference resolution."""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.contracts import (
    check_backend_capabilities, check_design_trace, check_revision_contracts,
)

ROOT = Path(__file__).resolve().parents[2]


class MetadataIds(unittest.TestCase):
    """Exercise complete trace metadata and registered Markdown identity boundaries."""

    def test_complete_trace_rejects_duplicate_requirements_and_verifications(self):
        original = ValidationContext(ROOT).load('spec/traceability.json')
        for group, label in (('requirements', 'requirement'), ('verification', 'verification')):
            mutated = copy.deepcopy(original)
            mutated[group].append(copy.deepcopy(mutated[group][0]))
            context = ValidationContext(ROOT)
            original_load = context.load
            with self.subTest(group=group):
                with patch.object(context, 'load', side_effect=lambda name:
                                  mutated if name == 'spec/traceability.json' else original_load(name)):
                    with self.assertRaisesRegex(AssertionError, 'Duplicate ' + label + ' ID'):
                        check_revision_contracts(context)
        context = ValidationContext(ROOT)
        check_revision_contracts(context)
        self.assertTrue(all(row['status'] == 'pass' for row in context.results))

    def test_duplicate_goal_declarations_do_not_collapse_into_valid_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docs').mkdir()
            (root / 'docs/technical-design.md').write_text((ROOT / 'docs/technical-design.md').read_text())
            tor = (ROOT / 'docs/terms-of-reference.md').read_text()
            goal = next(line for line in tor.splitlines() if line.startswith('| G1 '))
            (root / 'docs/terms-of-reference.md').write_text(tor.replace(goal + '\n', goal + '\n' + goal + '\n', 1))
            source = ValidationContext(ROOT)
            with self.assertRaisesRegex(AssertionError, 'Duplicate goal ID'):
                check_design_trace(ValidationContext(root), source.load('spec/roadmap.json')['phases'],
                                   source.load('spec/traceability.json'))

    def test_duplicate_source_headings_do_not_collapse_into_valid_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            context = ValidationContext(Path(directory))
            for path in context.markdown_paths():
                path.parent.mkdir(exist_ok=True)
                path.write_text('# Title\n')
            refs = (ROOT / 'docs/references.md').read_text()
            (context.root / 'docs/references.md').write_text(refs + '\n### D-TOR\n')
            capabilities = ValidationContext(ROOT).load('spec/backend-capabilities.json')
            with patch.object(context, 'load', return_value=capabilities):
                with self.assertRaisesRegex(AssertionError, 'Duplicate source ID'):
                    check_backend_capabilities(context)


    def test_source_citations_reject_lowercase_and_mixed_case_with_canonical_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            context = ValidationContext(Path(directory))
            for path in context.markdown_paths():
                path.parent.mkdir(exist_ok=True)
                path.write_text('# Title\n')
            (context.root / 'docs/references.md').write_text((ROOT / 'docs/references.md').read_text())
            capabilities = ValidationContext(ROOT).load('spec/backend-capabilities.json')
            variants = ('e-polars-null', 'E-Polars-Null', 'e-POLARS-NULL', 'd-tor', 'D-Tor')
            for source_id in variants:
                (context.root / 'README.md').write_text('# Title\n\n[' + source_id + ']\n')
                with self.subTest(source_id=source_id), patch.object(context, 'load', return_value=capabilities):
                    with self.assertRaisesRegex(AssertionError, 'Noncanonical source ID ' + source_id):
                        check_backend_capabilities(context)
            (context.root / 'README.md').write_text(
                '# Title\n\n[E-POLARS-NULL, D-TOR]. Identifier abc-d-other is unrelated.\n')
            with patch.object(context, 'load', return_value=capabilities):
                self.assertEqual(len(check_backend_capabilities(context)), len(capabilities['capabilities']))

    def test_source_register_rejects_noncanonical_heading_even_without_citations(self):
        with tempfile.TemporaryDirectory() as directory:
            context = ValidationContext(Path(directory))
            for path in context.markdown_paths():
                path.parent.mkdir(exist_ok=True)
                path.write_text('# Title\n')
            for source_id in ('e-unused', 'E-Unused', 'd-unused', 'D-Unused'):
                (context.root / 'docs/references.md').write_text('# References\n\n### ' + source_id + '\n')
                with self.subTest(source_id=source_id):
                    with self.assertRaisesRegex(AssertionError, 'Noncanonical source ID ' + source_id):
                        check_backend_capabilities(context)

    def test_capability_source_lists_require_exact_registered_case(self):
        source = ValidationContext(ROOT)
        capabilities = source.load('spec/backend-capabilities.json')
        for replacement in ('e-polars2-release', 'E-Polars2-Release'):
            mutated = copy.deepcopy(capabilities)
            mutated['capabilities'][0]['sources'][0] = replacement
            context = ValidationContext(ROOT)
            with self.subTest(source_id=replacement), patch.object(context, 'load', return_value=mutated):
                with self.assertRaisesRegex(AssertionError, 'Unresolved capability source'):
                    check_backend_capabilities(context)


if __name__ == '__main__':
    unittest.main()
