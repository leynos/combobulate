"""Check the cuprum boundary the proof scripts run verifiers through.

The scripts must read an exit status and the output together, treat a non-zero
exit as a result, and tell a verifier that failed from one that never started.
These tests pin each of those with ordinary shell programs.
"""

import tempfile
import unittest
from pathlib import Path

from captured_command import CapturedResult, run_captured


class StatusAndOutputTests(unittest.TestCase):
    """A finished command reports its status and both streams."""

    def test_output_is_stdout_then_stderr(self) -> None:
        """The two streams are joined in the order the parsers expect."""
        result = run_captured(['sh', '-c', 'echo out; echo err >&2'])
        self.assertEqual(result, CapturedResult(0, 'out\nerr\n'))

    def test_a_non_zero_exit_is_returned_not_raised(self) -> None:
        """A failing proof is a result for the caller to interpret."""
        result = run_captured(['sh', '-c', 'exit 3'])
        self.assertEqual(result.exit_code, 3)


class ContextTests(unittest.TestCase):
    """The directory and environment apply to the child only."""

    def test_the_working_directory_applies(self) -> None:
        """The command runs where the caller asked."""
        with tempfile.TemporaryDirectory() as name:
            result = run_captured(['pwd'], cwd=Path(name))
            self.assertEqual(result.output.strip(), str(Path(name).resolve()))

    def test_variables_are_overlaid_for_the_child(self) -> None:
        """A named variable reaches the child and the live environment stays."""
        result = run_captured(['sh', '-c', 'echo "$PROBE_VALUE"'], env={'PROBE_VALUE': 'set'})
        self.assertEqual(result.output.strip(), 'set')

    def test_env_dash_u_unsets_an_inherited_variable(self) -> None:
        """Unsetting goes through ``env -u``, which overlaying cannot do."""
        result = run_captured(
            ['env', '-u', 'PROBE_VALUE', 'sh', '-c', 'echo "[$PROBE_VALUE]"'],
            env={'PROBE_VALUE': 'set'},
        )
        self.assertEqual(result.output.strip(), '[]')


class FailureToStartTests(unittest.TestCase):
    """A verifier that never started is not a failed proof."""

    def test_a_missing_program_raises(self) -> None:
        """The caller must see a missing verifier as itself."""
        with self.assertRaises(FileNotFoundError):
            run_captured(['definitely-not-a-program'])

    def test_an_empty_command_is_refused(self) -> None:
        """There is nothing to register in the catalogue."""
        with self.assertRaises(ValueError):
            run_captured([])


if __name__ == '__main__':
    unittest.main()
