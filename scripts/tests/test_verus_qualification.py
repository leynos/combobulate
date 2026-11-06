"""Qualify a Verus mutant only when its diagnostic names the seeded region.

The wiring probe accepts a candidate on exact verification counts and on a
single ``postcondition not satisfied`` diagnostic. These tests exercise that
location rule directly, so a diagnostic in a neighbouring function, another
file, or a repeated failure cannot stand in for the seeded mutant.
"""

import tempfile
import unittest
from pathlib import Path

from verifier_probe_loader import load_verifier_probes

# Line 8 holds the mutant's contract clause and line 10 its body. The region
# also reaches the doc comment on line 6, because Verus may name either.
MUTANT_SOURCE = """\
/// A helper declared before the mutant.
fn helper() -> u8 {
    1
}

/// The seeded mutant.
fn mutant() -> u8
    ensures result == 2
{
    1
}
"""

HELPER_ONLY_SOURCE = """\
/// A helper without a seeded mutant.
fn helper() -> u8 {
    1
}
"""


def _diagnostic(path: str, line: int) -> str:
    """Return one Verus postcondition diagnostic naming ``path`` and ``line``."""
    return (
        "error: postcondition not satisfied\n"
        f"  --> {path}:{line}:5\n"
        "   |\n"
        "   |     result == 2\n"
        "   |     ^^^^^^^^^^\n"
    )


class MutantLocationTests(unittest.TestCase):
    """Reject every failure that does not name the seeded mutant declaration."""

    def _write(self, directory: Path, source: str) -> Path:
        """Write ``source`` as ``mutant.rs`` inside ``directory``."""
        path = directory / "mutant.rs"
        path.write_text(source, encoding="utf-8")
        return path

    def test_diagnostic_inside_the_mutant_qualifies(self) -> None:
        """A contract clause inside the declaration must be accepted."""
        module = load_verifier_probes().verus_probe
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            source = self._write(directory, MUTANT_SOURCE)

            accepted = module._fails_at_mutant(
                _diagnostic(str(source), 8), source, directory
            )

        self.assertTrue(accepted, "the mutant's contract line must qualify")

    def test_diagnostic_in_the_preceding_function_is_rejected(self) -> None:
        """A neighbouring function's failure must not qualify as the mutant."""
        module = load_verifier_probes().verus_probe
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            source = self._write(directory, MUTANT_SOURCE)

            accepted = module._fails_at_mutant(
                _diagnostic(str(source), 2), source, directory
            )

        self.assertFalse(accepted, "a failure before the mutant must be rejected")

    def test_diagnostic_in_another_source_file_is_rejected(self) -> None:
        """A failure in a different candidate file must not qualify."""
        module = load_verifier_probes().verus_probe
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            source = self._write(directory, MUTANT_SOURCE)
            other = directory / "other.rs"
            other.write_text(MUTANT_SOURCE, encoding="utf-8")

            accepted = module._fails_at_mutant(
                _diagnostic(str(other), 8), source, directory
            )

        self.assertFalse(accepted, "a diagnostic in another file must be rejected")

    def test_relative_location_resolves_against_the_probe_directory(self) -> None:
        """A relative diagnostic path must name the candidate it resolves to."""
        module = load_verifier_probes().verus_probe
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            source = self._write(directory, MUTANT_SOURCE)

            accepted = module._fails_at_mutant(
                _diagnostic("mutant.rs", 10), source, directory
            )

        self.assertTrue(accepted, "a relative path resolving to the source must qualify")

    def test_two_postcondition_failures_are_rejected(self) -> None:
        """Exactly one failure may be attributed to the seeded mutant."""
        module = load_verifier_probes().verus_probe
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            source = self._write(directory, MUTANT_SOURCE)
            log = _diagnostic(str(source), 8) + _diagnostic(str(source), 10)

            accepted = module._fails_at_mutant(log, source, directory)

        self.assertFalse(accepted, "two failures cannot both name the mutant")

    def test_source_without_a_mutant_raises(self) -> None:
        """A candidate that lost its mutant declaration must fail loudly."""
        module = load_verifier_probes().verus_probe
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            source = self._write(directory, HELPER_ONLY_SOURCE)

            with self.assertRaisesRegex(RuntimeError, "no seeded mutant"):
                module._fails_at_mutant(_diagnostic(str(source), 2), source, directory)


if __name__ == "__main__":
    unittest.main()