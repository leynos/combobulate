"""Exercise ticked roadmap evidence through the composed closure checks."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.ledger import check_task_links
from docs_validation.roadmap_status import check_roadmap_status, roadmap_tasks


class TickedRoadmapIntegration(unittest.TestCase):
    """Check the checkbox ledger and evidence closure together on an isolated task."""

    def setUp(self):
        """Create an isolated repository containing one ticked, ungoverned task."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'docs').mkdir()
        (self.root / 'spec').mkdir()
        (self.root / 'docs/roadmap.md').write_text('- [x] 1.1.1. Example task.\n', encoding='utf-8')
        (self.root / 'docs/evidence.md').write_text('# Evidence\n', encoding='utf-8')
        self.roadmap = {'phases': [{'steps': [{'tasks': [
            {'id': '1.1.1', 'status': 'done', 'requires': []},
        ]}]}]}
        self.write_json('spec/roadmap.json', self.roadmap)
        self.write_json('spec/decisions.json', {'decisions': []})
        self.write_json('spec/proof-obligations.json', {'obligations': []})
        self.write_json('spec/traceability.json', {'requirements': [], 'verification': []})
        self.write_json('spec/task-completion.json', {'tasks': [{
            'task': '1.1.1', 'decisions': [], 'artefacts': ['docs/evidence.md'],
        }]})

    def write_json(self, relative_path: str, value: dict) -> None:
        """Write one checker input beneath the temporary repository root."""
        (self.root / relative_path).write_text(json.dumps(value), encoding='utf-8')

    def run_tick_checks(self) -> ValidationContext:
        """Run checkbox consistency and evidence closure as the composed task path."""
        context = ValidationContext(self.root)
        tasks = roadmap_tasks(context.load('spec/roadmap.json'))
        check_task_links(context, tasks)
        check_roadmap_status(context)
        return context

    def test_supported_tick_passes_without_inventing_a_decision(self):
        """Accept a tick whose evidence is complete although no decision governs it."""
        context = self.run_tick_checks()
        self.assertEqual(context.results[-1]['check'], 'roadmap-status',
                         'the composed closure check must record its result')
        self.assertEqual(context.results[-1]['count'], 1,
                         'the supported checkbox must be counted as ticked')

    def test_tick_without_completion_evidence_fails(self):
        """Reject a tick when the completion register has no matching record."""
        self.write_json('spec/task-completion.json', {'tasks': []})
        with self.assertRaisesRegex(AssertionError, 'no completion record'):
            self.run_tick_checks()

    def test_tick_with_unaccepted_citation_fails(self):
        """Reject a tick when its cited decision is not accepted."""
        self.write_json('spec/decisions.json', {'decisions': [
            {'id': 'D01', 'lifecycle': 'proposed'},
        ]})
        self.write_json('spec/task-completion.json', {'tasks': [{
            'task': '1.1.1', 'decisions': ['D01'], 'artefacts': ['docs/evidence.md'],
        }]})
        with self.assertRaisesRegex(AssertionError, 'decision D01 is proposed, not accepted'):
            self.run_tick_checks()


if __name__ == '__main__':
    unittest.main()
