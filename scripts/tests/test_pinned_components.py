"""Check that the build tools read the toolchain pin as parsed TOML.

The verifier-record digest parses ``rust-toolchain.toml``; the shell helper
that lists its components must agree, or a comment could hide a component from
the installer while the digest still matched.

For example::

    python3 -m unittest test_pinned_components
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from verifier_probe_loader import SCRIPTS


def components(toolchain: str) -> subprocess.CompletedProcess:
    """Run ``pinned_components`` against a toolchain file with this text."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'rust-toolchain.toml'
        path.write_text(toolchain, encoding='utf-8')
        return subprocess.run(
            ['bash', '-c', f'source "{SCRIPTS}/build-tools-common.sh"; pinned_components'],
            env={**os.environ, 'RUST_TOOLCHAIN_FILE': str(path)},
            capture_output=True,
            text=True,
            check=False,
        )


class PinnedComponentsTests(unittest.TestCase):
    """Exercise the component reader on layouts the old line match missed."""

    def test_a_trailing_comment_does_not_hide_a_component(self) -> None:
        """A comment after a component is layout, not content."""
        result = components(
            '[toolchain]\nchannel = "nightly"\ncomponents = [\n'
            '  "clippy", # lint\n  "rustfmt",  # format\n]\n'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ['clippy', 'rustfmt'], 'both listed')

    def test_a_single_line_array_is_read(self) -> None:
        """The array may sit on one line."""
        result = components('[toolchain]\ncomponents = ["clippy", "rustfmt"]\n')
        self.assertEqual(result.stdout.split(), ['clippy', 'rustfmt'], 'both listed')

    def test_an_empty_list_is_rejected(self) -> None:
        """A bare compiler is not a complete development toolchain."""
        result = components('[toolchain]\nchannel = "nightly"\n')
        self.assertNotEqual(result.returncode, 0, 'an empty list must fail')
        self.assertIn('no components found', result.stderr)


if __name__ == '__main__':
    unittest.main()
