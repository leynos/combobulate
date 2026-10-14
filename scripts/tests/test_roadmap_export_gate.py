"""Require the design checker to reject a stale roadmap export."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.ledger import check_roadmap_export
from export_roadmap import parse_roadmap

ROOT = Path(__file__).resolve().parents[2]


class RoadmapExportGate(unittest.TestCase):
    """The checker loads the exporter from scripts/ and compares its output."""

    def test_stale_committed_export_fails_the_checker(self) -> None:
        """Reject semantically stale JSON even when the Markdown source is unchanged."""
        context = ValidationContext(ROOT)
        stale = context.load('spec/roadmap.json')
        stale['phases'][0]['steps'][0]['tasks'][0]['title'] = 'Stale title.'
        original_load = context.load
        with patch.object(context, 'load', lambda name: stale if name == 'spec/roadmap.json' else original_load(name)):
            with self.assertRaisesRegex(AssertionError, 'Roadmap export drift'):
                check_roadmap_export(context)

    def test_export_preserves_completed_and_open_task_statuses(self):
        """Keep completed and open status when exporting the canonical roadmap."""
        roadmap = parse_roadmap((ROOT / 'docs/roadmap.md').read_text(encoding='utf-8'))
        tasks = {task['id']: task for phase in roadmap['phases']
                 for step in phase['steps'] for task in step['tasks']}
        self.assertEqual(tasks['1.1.1']['status'], 'done', 'a checked task must remain completed in the export')
        self.assertEqual(tasks['1.2.1']['status'], 'open', 'an unchecked task must remain open in the export')

    def test_current_committed_export_passes_the_checker(self) -> None:
        """Accept the checked-in export when it matches a fresh canonical-roadmap export."""
        check_roadmap_export(ValidationContext(ROOT))

    def test_whitespace_only_export_drift_fails_the_checker(self) -> None:
        """Treat trailing whitespace and a missing final newline as serialized-file drift."""
        export_path = ROOT / 'spec/roadmap.json'
        committed = export_path.read_text(encoding='utf-8')
        drifted_exports = (committed + ' ', committed.rstrip('\n'))
        files = ('docs/roadmap.md', 'scripts/export_roadmap.py', 'spec/roadmap.json')

        for drifted in drifted_exports:
            with self.subTest(trailing_text=repr(drifted[-4:])):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    for name in ('docs', 'scripts', 'spec'):
                        (root / name).mkdir()
                    for name in files:
                        shutil.copyfile(ROOT / name, root / name)
                    (root / 'spec/roadmap.json').write_text(drifted, encoding='utf-8')
                    with self.assertRaisesRegex(AssertionError, 'Roadmap export drift'):
                        check_roadmap_export(ValidationContext(root))

    def test_loading_exporter_removes_temporary_module_registration(self) -> None:
        """Keep a successful path-based import from leaving checker state in sys.modules."""
        module_name = '_design_pack_scripts_export_roadmap'
        previous = sys.modules.pop(module_name, None)
        try:
            ValidationContext(ROOT).load_script('export_roadmap.py')
            self.assertNotIn(module_name, sys.modules,
                             'path-loaded exporter must not remain in the global module registry')
        finally:
            if previous is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous

    def test_loading_exporter_restores_previous_module_registration(self) -> None:
        """Preserve another module occupying the checker's private import name."""
        module_name = '_design_pack_scripts_export_roadmap'
        previous = sys.modules.get(module_name)
        sentinel = ModuleType(module_name)
        sys.modules[module_name] = sentinel
        try:
            ValidationContext(ROOT).load_script('export_roadmap.py')
            self.assertIs(sys.modules[module_name], sentinel,
                          'path-loaded exporter must restore the previous registry entry')
        finally:
            if previous is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous

    def test_failed_module_execution_cleans_up_temporary_registration(self) -> None:
        """Restore global module state when a path-loaded script raises during execution."""
        module_name = '_design_pack_scripts_broken'
        previous = sys.modules.pop(module_name, None)
        try:
            with tempfile.TemporaryDirectory() as directory:
                scripts = Path(directory) / 'scripts'
                scripts.mkdir()
                script = scripts / 'broken.py'
                script.write_text("raise RuntimeError('intentional load failure')\n")
                with self.assertRaisesRegex(RuntimeError, 'intentional load failure'):
                    ValidationContext.load_module(script)
            self.assertNotIn(module_name, sys.modules,
                             'failed import must not leave a partial module registered')
        finally:
            if previous is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous


if __name__ == '__main__':
    unittest.main()
