"""Prove the canonical Markdown roadmap exports losslessly to its JSON view."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from hypothesis import event, given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from docs_validation.context import ValidationContext
from docs_validation.ledger import check_roadmap_export
from docs_validation.roadmap_markdown import (
    END, START, RoadmapStructureError, export_text, parse_roadmap,
)
from support.roadmap_render import render_document

ROOT = Path(__file__).resolve().parents[2]
ROADMAP = (ROOT / 'docs/roadmap.md').read_text(encoding='utf-8')


def committed_export() -> dict:
    """Load the committed JSON view that the drift check protects."""
    return json.loads((ROOT / 'spec/roadmap.json').read_text(encoding='utf-8'))


def replace_once(text: str, old: str, new: str) -> str:
    """Edit one exact occurrence so each negative control changes one item."""
    assert text.count(old) == 1, f'expected exactly one occurrence of {old!r}'
    return text.replace(old, new)


class RealRoadmapExport(unittest.TestCase):
    """The committed export must equal a fresh export of the canonical roadmap."""

    def test_export_matches_committed_json_view(self):
        self.assertEqual(parse_roadmap(ROADMAP), committed_export(),
                         'docs/roadmap.md must export exactly to spec/roadmap.json')

    def test_serialized_export_is_byte_identical_and_deterministic(self):
        committed = (ROOT / 'spec/roadmap.json').read_text(encoding='utf-8')
        self.assertEqual(export_text(ROADMAP), committed, 'serialization must match the committed file')
        self.assertEqual(export_text(ROADMAP), export_text(ROADMAP), 'export must be deterministic')

    def test_export_is_independent_of_paragraph_wrapping(self):
        rewrapped = replace_once(ROADMAP, 'Record the scope, decision authority, licence, and pre-1.0 API\n  policy.',
                                 'Record the scope, decision authority, licence, and\n  pre-1.0 API policy.')
        self.assertEqual(parse_roadmap(rewrapped), parse_roadmap(ROADMAP), 'wrapping must not change the export')

    def test_open_checkboxes_export_as_open_status(self):
        statuses = {task['status'] for phase in parse_roadmap(ROADMAP)['phases']
                    for step in phase['steps'] for task in step['tasks']}
        self.assertEqual(statuses, {'open'}, 'every task is open before roadmap step 1.1 completes')


class DriftNegativeControls(unittest.TestCase):
    """Each single-item Markdown edit must change the export at that item."""

    def first_task(self, roadmap: dict) -> dict:
        return roadmap['phases'][0]['steps'][0]['tasks'][0]

    def test_changed_title_changes_export(self):
        edited = replace_once(ROADMAP, '1.1.1. Record the scope', '1.1.1. Record only the scope')
        self.assertNotEqual(self.first_task(parse_roadmap(edited))['title'], self.first_task(committed_export())['title'],
                            'a retitled task must drift from the committed export')

    def test_changed_dependency_changes_export(self):
        edited = replace_once(ROADMAP, 'Requires 1.1.1, 1.1.2, 1.1.3.', 'Requires 1.1.1, 1.1.3.')
        task = parse_roadmap(edited)['phases'][0]['steps'][0]['tasks'][3]
        self.assertEqual(task['requires'], ['1.1.1', '1.1.3'], 'the edited Requires line must be exported')

    def test_ticked_checkbox_changes_status(self):
        edited = replace_once(ROADMAP, '- [ ] 1.1.1. Record', '- [x] 1.1.1. Record')
        self.assertEqual(self.first_task(parse_roadmap(edited))['status'], 'done', 'a tick must export as done')


class CheckerDriftGate(unittest.TestCase):
    """The design checker must reject a committed export that no longer matches."""

    def test_stale_committed_export_fails_the_checker(self):
        stale = committed_export()
        stale['phases'][0]['steps'][0]['tasks'][0]['title'] = 'Stale title.'
        context = ValidationContext(ROOT)
        original_load = context.load
        with patch.object(context, 'load', lambda name: stale if name == 'spec/roadmap.json' else original_load(name)):
            with self.assertRaisesRegex(AssertionError, 'Roadmap export drift'):
                check_roadmap_export(context)

    def test_current_committed_export_passes_the_checker(self):
        check_roadmap_export(ValidationContext(ROOT))


class MalformedStructure(unittest.TestCase):
    """Unknown structure fails with a source line instead of being dropped."""

    def assert_rejected_at_line(self, text: str, line: int) -> None:
        with self.assertRaises(RoadmapStructureError) as raised:
            parse_roadmap(text)
        self.assertEqual(raised.exception.line, line, f'error must name line {line}: {raised.exception}')

    def test_missing_markers_are_rejected(self):
        with self.assertRaisesRegex(RoadmapStructureError, 'exactly one'):
            parse_roadmap('# Roadmap\n')

    def test_heading_at_wrong_level_is_rejected(self):
        text = f'Revision 0.2, 6 October 2026.\n\n{START}\n\n#### 1. Too deep\n\n{END}\n'
        self.assert_rejected_at_line(text, 5)

    def test_task_without_checkbox_is_rejected(self):
        bad = replace_once(ROADMAP, '- [ ] 1.1.1. Record', '- 1.1.1. Record')
        line = ROADMAP[:ROADMAP.index('- [ ] 1.1.1. Record')].count('\n') + 1
        self.assert_rejected_at_line(bad, line)

    def test_unlabelled_task_bullet_is_rejected(self):
        bad = replace_once(ROADMAP, '  - Requires 1.1.1, 1.1.2, 1.1.3.', '  - Mystery note.')
        line = ROADMAP[:ROADMAP.index('  - Requires 1.1.1, 1.1.2, 1.1.3.')].count('\n') + 1
        self.assert_rejected_at_line(bad, line)


WORDS = st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=8)
SENTENCE = st.lists(WORDS, min_size=1, max_size=12).map(lambda words: ' '.join(words).capitalize() + '.')
IDS = st.lists(st.sampled_from(['B01', 'B02', 'B03']), min_size=1, max_size=3, unique=True)


@st.composite
def roadmaps(draw) -> dict:
    """Draw small, well-formed roadmap structures in canonical numbering."""
    phases = []
    task_ids: list[str] = []
    for phase_number in range(1, draw(st.integers(1, 3)) + 1):
        steps = []
        for step_index in range(1, draw(st.integers(1, 2)) + 1):
            tasks = []
            for task_index in range(1, draw(st.integers(1, 3)) + 1):
                task_id = f'{phase_number}.{step_index}.{task_index}'
                requires = draw(st.lists(st.sampled_from(task_ids), max_size=2, unique=True)) if task_ids else []
                tasks.append({
                    'id': task_id, 'title': draw(SENTENCE), 'requires': requires,
                    'sections': f'§§{draw(st.integers(1, 19))}', 'success': draw(SENTENCE),
                    'details': draw(st.lists(SENTENCE, max_size=2)), 'proof_first': draw(SENTENCE),
                    'bets': draw(IDS), 'status': draw(st.sampled_from(['open', 'done'])),
                })
                task_ids.append(task_id)
            steps.append({'number': f'{phase_number}.{step_index}', 'title': draw(SENTENCE).rstrip('.'),
                          'question': draw(SENTENCE), 'sections': f'§§{draw(st.integers(1, 19))}', 'tasks': tasks})
        phases.append({'number': phase_number, 'title': draw(SENTENCE).rstrip('.'), 'idea': draw(SENTENCE),
                       'goals': draw(st.lists(st.sampled_from(['G1', 'G2', 'G3']), min_size=1, max_size=3,
                                              unique=True)),
                       'gate': draw(SENTENCE), 'context': draw(SENTENCE), 'steps': steps})
    return {'revision': '0.2', 'phases': phases}


class RenderedRoundTrip(unittest.TestCase):
    """An independent renderer's layout must export back to the drawn structure."""

    def test_render_then_export_round_trips(self):
        seen: set[str] = set()

        @settings(derandomize=True, max_examples=60, deadline=None)
        @given(roadmaps())
        def round_trip(structure: dict) -> None:
            tasks = [task for phase in structure['phases'] for step in phase['steps'] for task in step['tasks']]
            classes = {
                'multi-phase' if len(structure['phases']) > 1 else 'single-phase',
                'has-details' if any(task['details'] for task in tasks) else 'no-details',
                'has-requires' if any(task['requires'] for task in tasks) else 'no-requires',
                'has-done' if any(task['status'] == 'done' for task in tasks) else 'all-open',
            }
            for name in classes:
                event(name)
            seen.update(classes)
            exported = parse_roadmap(render_document(structure))
            expected = copy.deepcopy(structure)
            expected['status'] = exported['status']
            self.assertEqual(exported, expected, 'rendered roadmap must export to the drawn structure')

        round_trip()
        required = {'multi-phase', 'single-phase', 'has-details', 'no-details', 'has-requires', 'has-done',
                    'all-open'}
        self.assertTrue(required <= seen, f'generator never produced {sorted(required - seen)}')


if __name__ == '__main__':
    unittest.main()
