"""Keep the Design contracts workflow and Make invocation wired together."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class DesignWorkflowContract(unittest.TestCase):
    """Check that workflow-selected inputs reach the reproducible design check."""

    def test_workflow_passes_base_and_scheduled_date_to_make(self):
        """Preserve full history and connect selected workflow outputs to Make."""
        workflow = yaml.load(
            (ROOT / '.github/workflows/design.yml').read_text(encoding='utf-8'),
            Loader=yaml.BaseLoader,
        )
        checkout = workflow['jobs']['design-check']['steps'][0]
        self.assertEqual(checkout['with']['fetch-depth'], '0',
                         'freeze checks need the merge base in checkout history')

        steps = workflow['jobs']['design-check']['steps']
        base_step = next(step for step in steps if step.get('id') == 'base')
        self.assertIn('git merge-base "origin/$BASE_REF" HEAD', base_step['run'],
                      'pull requests must compare frozen decisions with their merge base')
        self.assertIn('date -u +%F', base_step['run'],
                      'scheduled expiry checks must use the workflow run date')

        check_step = next(step for step in steps if step.get('name') == 'Validate documentation contracts')
        self.assertEqual(check_step['env']['BASE_REV'], '${{ steps.base.outputs.rev }}',
                         'the selected revision must reach Make as BASE_REV')
        self.assertEqual(check_step['env']['RUN_DATE'], '${{ steps.base.outputs.as_of }}',
                         'the scheduled date must reach Make as RUN_DATE')
        self.assertIn('make design-check BASE_REV="$BASE_REV"', check_step['run'],
                      'the workflow must invoke the Make target with its base revision')
        self.assertIn('AS_OF="$RUN_DATE"', check_step['run'],
                      'the workflow must pass a scheduled evaluation date')

    def test_make_forwards_as_of_and_base_revision_to_checker(self):
        """Keep Make's design-check arguments aligned with its workflow inputs."""
        result = subprocess.run(
            ['make', '--no-print-directory', '--dry-run', 'design-check',
             'BASE_REV=fixture-base', 'AS_OF=2026-10-15'],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        self.assertIn('tools/check_docs.py --as-of 2026-10-15 --base-rev fixture-base', result.stdout,
                      'the checker must receive both Make variables')


if __name__ == '__main__':
    unittest.main()
