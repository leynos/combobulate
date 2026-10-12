"""Require the design checker to reject a stale roadmap export."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.ledger import check_roadmap_export

ROOT = Path(__file__).resolve().parents[2]


class RoadmapExportGate(unittest.TestCase):
    """The checker loads the exporter from scripts/ and compares its output."""

    def test_stale_committed_export_fails_the_checker(self):
        context = ValidationContext(ROOT)
        stale = context.load('spec/roadmap.json')
        stale['phases'][0]['steps'][0]['tasks'][0]['title'] = 'Stale title.'
        original_load = context.load
        with patch.object(context, 'load', lambda name: stale if name == 'spec/roadmap.json' else original_load(name)):
            with self.assertRaisesRegex(AssertionError, 'Roadmap export drift'):
                check_roadmap_export(context)

    def test_current_committed_export_passes_the_checker(self):
        check_roadmap_export(ValidationContext(ROOT))


if __name__ == '__main__':
    unittest.main()
