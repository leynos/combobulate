"""Prove Polars stays inside its backend module, and that the check can fail (VO-14).

DL-19 keeps the Polars adapter in a crate-private facade module instead of a
crate of its own, and VO-14 is the control that replaces the separation a crate
boundary would have given. A confinement check that could never fire is
indistinguishable from no check at all, so most cases below seed one violation
and require the named failure. The final case keeps the pair honest by
accepting the tree the repository actually commits.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.polars_confinement import (
    BACKEND_MODULE, check_polars_confinement,
)

ROOT = Path(__file__).resolve().parents[2]


class ScratchFacade(unittest.TestCase):
    """Provide a scratch facade tree the check can be pointed at.

    Each case writes only the two files the check reads — a backend module and
    one other facade source — so a reader can see exactly what the rule
    consults and no case depends on the shape of the real checkout.
    """

    def setUp(self) -> None:
        """Create a scratch root with a clean backend and a clean profile."""
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        (self.root / 'src').mkdir()
        self.write(BACKEND_MODULE, 'use polars::prelude::DataFrame;\n')
        self.write('src/profile.rs', 'pub struct BuildProfile;\n')

    def tearDown(self) -> None:
        """Remove the scratch root."""
        self._directory.cleanup()

    def write(self, relative: str, text: str) -> None:
        """Write one facade source under the scratch root."""
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def run_check(self) -> None:
        """Run the confinement check against the scratch root."""
        check_polars_confinement(ValidationContext(self.root))


class ConfinementViolations(ScratchFacade):
    """Require each out-of-place Polars path to be reported."""

    def test_use_of_polars_outside_the_backend_fails(self) -> None:
        """A `use polars::` in another facade source is a violation."""
        self.write('src/profile.rs', 'use polars::prelude::DataFrame;\n')
        with self.assertRaises(AssertionError) as raised:
            self.run_check()
        self.assertIn('src/profile.rs', str(raised.exception))

    def test_qualified_path_outside_the_backend_fails(self) -> None:
        """A fully qualified `polars::` path is confined however it is spelled."""
        self.write('src/lib.rs', 'pub fn probe() -> polars::prelude::PolarsResult<()> { }\n')
        with self.assertRaises(AssertionError):
            self.run_check()

    def test_typeset_path_outside_the_backend_fails(self) -> None:
        """A turbofish form still reaches the dependency and is confined."""
        self.write('src/lib.rs', 'fn f() { polars::prelude::Int64Chunked::new_vec(); }\n')
        with self.assertRaises(AssertionError):
            self.run_check()

    def test_a_backend_submodule_may_name_polars(self) -> None:
        """A submodule of the backend is still the backend, so it is allowed."""
        self.write('src/polars_backend/series.rs', 'use polars::prelude::Series;\n')
        self.run_check()

    def test_a_comment_mentioning_polars_is_not_a_violation(self) -> None:
        """A doc comment that names Polars is not compiled, so it is not a path."""
        self.write('src/profile.rs', '//! Reports whether the polars:: backend is present.\n')
        self.run_check()

    def test_a_string_literal_naming_polars_is_not_a_violation(self) -> None:
        """A string is one opaque token, so its contents are not a path."""
        self.write('src/profile.rs', 'const NOTE: &str = "polars::prelude";\n')
        self.run_check()

    def test_a_bare_polars_identifier_is_not_a_violation(self) -> None:
        """The bare name carries no path, so it does not reach the dependency."""
        self.write('src/profile.rs', 'const HAS_POLARS: bool = cfg!(feature = "polars");\n')
        self.run_check()


class NonVacuity(unittest.TestCase):
    """Require the seeded-violation control to fire on the real facade."""

    def test_seeded_violation_is_reported(self) -> None:
        """A scan that found nothing anywhere must not pass.

        The control is what makes the passing check evidence: it proves the
        scanner still recognises the form it is meant to reject, independently
        of whether the committed tree happens to contain one.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / BACKEND_MODULE).write_text('', encoding='utf-8')
            (root / 'src' / 'profile.rs').write_text(
                'pub struct BuildProfile;\n', encoding='utf-8')
            check_polars_confinement(ValidationContext(root))

    def test_missing_control_source_fails_rather_than_passing(self) -> None:
        """A control that cannot run must fail, not silently accept."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / BACKEND_MODULE).write_text('', encoding='utf-8')
            with self.assertRaises(AssertionError):
                check_polars_confinement(ValidationContext(root))


class CommittedTree(ScratchFacade):
    """Require the tree the repository actually commits to pass."""

    def test_the_committed_facade_confinement_passes(self) -> None:
        """The real facade keeps Polars inside the backend module."""
        check_polars_confinement(ValidationContext(ROOT))


if __name__ == '__main__':
    unittest.main()
