"""Verify committed evidence without overwriting stale, malformed, or falsified reports."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_docs

ROOT = Path(__file__).resolve().parents[2]


class ValidationReport(unittest.TestCase):
    """Run the complete checker on copied source inputs and inspect persistent side effects."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for folder in ('docs', 'spec', 'tools'):
            shutil.copytree(ROOT / folder, self.root / folder, ignore=shutil.ignore_patterns('__pycache__'))
        for path in ROOT.iterdir():
            if path.is_file():
                shutil.copy2(path, self.root / path.name)
        self.report = self.root / 'docs/validation-results.json'
        self.assertEqual(self.run_main(['--write']), 0)

    def run_main(self, arguments: list[str]) -> int:
        """Execute the checker against copied inputs and capture its evidence output."""
        with patch.object(check_docs, 'ROOT', self.root), contextlib.redirect_stdout(io.StringIO()):
            return check_docs.main(arguments)

    def source_bytes(self) -> dict[str, bytes]:
        """Snapshot repository inputs and report, excluding incidental Python caches."""
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*')
                if path.is_file() and '__pycache__' not in path.parts}

    def test_successful_default_check_does_not_mutate_inputs_or_report(self):
        before = self.source_bytes()
        self.assertEqual(self.run_main([]), 0)
        self.assertEqual(self.source_bytes(), before)

    def test_invalid_json_report_is_rejected_without_replacement(self):
        self.report.write_text('{')
        before = self.source_bytes()
        with self.assertRaises(SystemExit):
            self.run_main([])
        self.assertEqual(self.source_bytes(), before)

    def test_stale_and_falsified_reports_fail_without_mutation(self):
        original = json.loads(self.report.read_text())
        mutations = ('count', 'status', 'not_run')
        for mutation in mutations:
            report = json.loads(json.dumps(original))
            if mutation == 'count':
                next(row for row in report['checks'] if row.get('count') == 1)['count'] = True
            elif mutation == 'status':
                report['status'] = 'fail'
            else:
                report['not_run'] = []
            self.report.write_text(json.dumps(report) + '\n')
            before = self.source_bytes()
            with self.subTest(mutation=mutation), self.assertRaisesRegex(SystemExit, 'Validation report drift'):
                self.run_main([])
            self.assertEqual(self.source_bytes(), before)

    def test_source_failure_leaves_report_untouched_even_with_write_requested(self):
        (self.root / 'spec/cost-cases.json').write_text('{')
        for arguments in ([], ['--write']):
            before = self.source_bytes()
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                self.run_main(arguments)
            self.assertEqual(self.source_bytes(), before)

    def test_explicit_write_repairs_report_after_source_validation(self):
        self.report.write_text('{')
        before = self.source_bytes()
        self.assertEqual(self.run_main(['--write']), 0)
        after = self.source_bytes()
        self.assertEqual({key for key in before if before[key] != after[key]},
                         {'docs/validation-results.json'})
        self.assertEqual(json.loads(self.report.read_text())['status'], 'pass')
        self.assertEqual(self.run_main([]), 0)


if __name__ == '__main__':
    unittest.main()
