"""Require the design checker to reject a stale roadmap export."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_docs import LEDGER_DEPENDENCIES
from docs_validation.context import ValidationContext
from docs_validation.ledger import check_roadmap_export
from export_roadmap import parse_roadmap

ROOT = Path(__file__).resolve().parents[2]


class RoadmapExportGate(unittest.TestCase):
    """The checker receives isolated roadmap collaborators and compares its output."""

    def test_stale_committed_export_fails_the_checker(self) -> None:
        """Reject semantically stale JSON even when the Markdown source is unchanged."""
        context = ValidationContext(ROOT)
        stale = context.load('spec/roadmap.json')
        stale['phases'][0]['steps'][0]['tasks'][0]['title'] = 'Stale title.'
        original_load = context.load
        with patch.object(context, 'load', lambda name: stale if name == 'spec/roadmap.json' else original_load(name)):
            with self.assertRaisesRegex(AssertionError, 'Roadmap export drift'):
                check_roadmap_export(context, LEDGER_DEPENDENCIES)

    def test_export_preserves_completed_and_open_task_statuses(self):
        """Keep completed and open status when exporting the canonical roadmap."""
        roadmap = parse_roadmap((ROOT / 'docs/roadmap.md').read_text(encoding='utf-8'))
        tasks = {task['id']: task for phase in roadmap['phases']
                 for step in phase['steps'] for task in step['tasks']}
        self.assertEqual(tasks['1.1.1']['status'], 'done', 'a checked task must remain completed in the export')
        self.assertEqual(tasks['1.2.1']['status'], 'open', 'an unchecked task must remain open in the export')

    def test_current_committed_export_passes_the_checker(self) -> None:
        """Accept the checked-in export when it matches a fresh canonical-roadmap export."""
        check_roadmap_export(ValidationContext(ROOT), LEDGER_DEPENDENCIES)

    def test_whitespace_only_export_drift_fails_the_checker(self) -> None:
        """Treat trailing whitespace and a missing final newline as serialized-file drift."""
        export_path = ROOT / 'spec/roadmap.json'
        committed = export_path.read_text(encoding='utf-8')
        drifted_exports = (committed + ' ', committed.rstrip('\n'))
        files = ('docs/roadmap.md', 'spec/roadmap.json')

        for drifted in drifted_exports:
            with self.subTest(trailing_text=repr(drifted[-4:])):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    for name in ('docs', 'spec'):
                        (root / name).mkdir()
                    for name in files:
                        shutil.copyfile(ROOT / name, root / name)
                    (root / 'spec/roadmap.json').write_text(drifted, encoding='utf-8')
                    with self.assertRaisesRegex(AssertionError, 'Roadmap export drift'):
                        check_roadmap_export(ValidationContext(root), LEDGER_DEPENDENCIES)

    def test_export_check_does_not_change_process_modules(self) -> None:
        """Keep injected exporters from adding or replacing process-global modules."""
        before = sys.modules.copy()
        check_roadmap_export(ValidationContext(ROOT), LEDGER_DEPENDENCIES)
        self.assertEqual(set(sys.modules), set(before), 'the check must not add process-global modules')
        self.assertTrue(all(sys.modules[name] is module for name, module in before.items()),
                        'the check must not replace process-global modules')


if __name__ == '__main__':
    unittest.main()
