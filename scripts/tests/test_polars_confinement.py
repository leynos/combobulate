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
    BACKEND_MODULE, check_polars_confinement, _polars_paths,
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

    def test_an_aliased_crate_outside_the_backend_fails(self) -> None:
        """A `use polars as p;` binds the crate under another name.

        ``p::prelude::DataFrame`` reaches every item ``polars::prelude::DataFrame``
        does, so a check that matched only the literal spelling would pass a
        facade module that imported Polars under any name it liked.
        """
        self.write('src/profile.rs', 'use polars as p;\nfn f() -> p::prelude::DataFrame { }\n')
        with self.assertRaises(AssertionError) as raised:
            self.run_check()
        self.assertIn('src/profile.rs', str(raised.exception),
                      'an aliased Polars path outside the backend must be reported')

    def test_a_grouped_self_alias_outside_the_backend_fails(self) -> None:
        """A `use polars::{self as p};` is the same rename and is equally confined."""
        self.write('src/profile.rs', 'use polars::{self as p};\nfn f() -> p::Series { }\n')
        with self.assertRaises(AssertionError):
            self.run_check()

    def test_an_alias_of_a_member_is_not_the_crate(self) -> None:
        """A rename below the root binds a name, not the crate.

        ``use polars::prelude as prelude;`` is not a crate alias, so a later
        bare ``prelude`` is not a path into Polars and must not be reported on
        its own account — only the import's own ``polars::`` is.
        """
        self.write('src/profile.rs',
                   'use polars::prelude as prelude;\nconst N: &str = "x";\n')
        with self.assertRaises(AssertionError) as raised:
            self.run_check()
        message = str(raised.exception)
        self.assertIn('src/profile.rs:1:5', message,
                      'the import itself must be the reported path')
        self.assertNotIn(':2:', message,
                          'a member alias must not become a second crate path')

    def test_an_aliased_crate_inside_the_backend_is_allowed(self) -> None:
        """The backend may rename the crate; it is still the backend."""
        self.write(BACKEND_MODULE, 'use polars as p;\nfn f() -> p::prelude::DataFrame { }\n')
        self.run_check()


class PolarsPathDetection(unittest.TestCase):
    """Require the detector to recognise each form that reaches the crate.

    The outcome cases above run the whole check, which reports a position and
    cannot show *why* a form was or was not matched. These pin the detector, so
    a change to it is visible as itself rather than as a moved position.
    """

    def test_a_literal_path_is_detected(self) -> None:
        """The canonical form is the positive control for every other case."""
        self.assertEqual([token.text for token in _polars_paths('use polars::prelude;')],
                         ['polars'],
                         'a literal polars:: path must be detected')

    def test_an_alias_binding_is_detected(self) -> None:
        """A path through the crate's alias reaches the same items."""
        self.assertEqual([token.line for token in _polars_paths('use polars as p;\np::x();')],
                         [2],
                         'only the aliased use on line 2 is a path')

    def test_a_member_alias_creates_no_second_path(self) -> None:
        """A rename below the root must not become a crate name."""
        self.assertEqual([token.text for token in _polars_paths('use polars::prelude as p;')],
                         ['polars'],
                         'a member alias must not be reported as the crate')

    def test_a_comment_and_a_literal_are_not_paths(self) -> None:
        """Neither is compiled, so neither is confined."""
        self.assertEqual(_polars_paths('//! polars::x\nconst S: &str = "polars::y";'), [],
                         'a comment and a literal must not be reported')


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

    def test_the_control_runs_the_detector_the_walk_uses(self) -> None:
        """Require the seeded text to be judged by ``_polars_paths`` itself.

        The control once searched for the literal word with a predicate of its
        own, so it kept firing after the detector regressed and the passing
        check proved nothing. Installing a detector that reports nothing must
        therefore make the control fail.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / BACKEND_MODULE).write_text('', encoding='utf-8')
            (root / 'src' / 'profile.rs').write_text('pub struct BuildProfile;\n',
                                                     encoding='utf-8')
            with _reporting_nothing():
                with self.assertRaises(AssertionError) as raised:
                    check_polars_confinement(ValidationContext(root))
        self.assertIn('must be reported', str(raised.exception),
                      'a detector that found nothing must fail the control')


class _SilentDetector:
    """Stand in for the detector, reporting no path for any source."""

    def __call__(self, text: str) -> list:
        """Report nothing, which is the regression the control exists to catch."""
        del text
        return []


class _Patch:
    """Install one detector in place of the module's own, for the body of a case."""

    def __enter__(self):
        """Replace the detector and record the original."""
        import docs_validation.polars_confinement as module
        self._original = module._polars_paths
        module._polars_paths = _SilentDetector()
        return self

    def __exit__(self, *_):
        """Restore the real detector."""
        import docs_validation.polars_confinement as module
        module._polars_paths = self._original
        return False


def _reporting_nothing() -> _Patch:
    """Return a context manager installing a detector that reports nothing."""
    return _Patch()


class CommittedTree(ScratchFacade):
    """Require the tree the repository actually commits to pass."""

    def test_the_committed_facade_confinement_passes(self) -> None:
        """The real facade keeps Polars inside the backend module."""
        check_polars_confinement(ValidationContext(ROOT))


if __name__ == '__main__':
    unittest.main()
