"""Reject malformed marked JSON fences in published Markdown examples."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from markdown_examples import load_marked_json_examples


class MarkedJsonExamples(unittest.TestCase):
    """Keep malformed source fences from being silently ignored."""

    def test_rejects_fence_without_marker(self):
        """Require every JSON fence to have its adjacent tested-example marker."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'examples.md'
            path.write_text('```json\n{}\n```\n', encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'fenced examples must have tested-example markers'):
                load_marked_json_examples(path)

    def test_rejects_unterminated_fence(self):
        """Report a marked JSON fence whose closing delimiter is missing."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'examples.md'
            path.write_text('<!-- tested-example: sample -->\n```json\n{}\n', encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'unterminated tested-example fence'):
                load_marked_json_examples(path)


if __name__ == '__main__':
    unittest.main()
