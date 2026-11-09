"""Prove VO-10's own check notices a trust audit that has stopped working (VO-10).

The scanner tests establish what the audit reports. This module establishes
that ``check_trust_audit`` would say so if the audit went quiet, which is the
guarantee VO-10 asks for: a check that only ever asserted emptiness would pass
against a scanner that reported nothing at all.

Two halves do that. The repository cases require the check to pass against the
seeded corpus as committed, so the seeded items are still found. The
deliberately-broken scanners then show the check refusing each direction — an
item in a shipped crate, and an item missing from the corpus.

Examples
--------
>>> callable(check_trust_audit)
True
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.trust_audit import AuditedFile, TrustItem, audit_tree, scan
from docs_validation.trust_audit_check import (
    SEEDED_ITEMS, _entry_points, _shipped_items, check_trust_audit,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS = 'tools/verifier-fixtures/kani-corpus/src/harnesses.rs'


class NestedMemberTargets(unittest.TestCase):
    """Require Cargo's target list to resolve for a member below the root.

    ``cargo metadata`` reports ``targets[].src_path`` as an absolute path under
    the workspace root, and the check makes it repository-relative before
    joining it back. Joining it to the *member's* directory instead repeats the
    member's own path and the target does not exist — silently, because the
    conventional ``src/lib.rs`` fallback still finds that file. Only the
    targets no fallback covers, such as an integration test or a ``build.rs``,
    would be dropped, and their trust vocabulary with them.
    """

    def setUp(self):
        """Create a workspace whose only member sits below the root."""
        import tempfile
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        self._write('Cargo.toml', '[workspace]\nmembers = ["crates/inner"]\nresolver = "3"\n')
        self._write('crates/inner/Cargo.toml',
                    '[package]\nname = "inner"\nversion = "0.1.0"\nedition = "2024"\n')
        self._write('crates/inner/src/lib.rs', 'pub fn lib() {}\n')
        self._write('crates/inner/build.rs', 'fn main() { kani::assume(x); }\n')
        self._write('crates/inner/tests/probe.rs', 'fn f() { kani::stub(a, b); }\n')

    def _write(self, relative, text):
        """Write one scratch file, creating its directories."""
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')

    def test_a_nested_target_resolves_once_not_twice(self):
        """Require each target path to be joined to the repository root."""
        crate_root = self.root / 'crates' / 'inner'
        resolved = {path.relative_to(self.root).as_posix()
                    for path in _entry_points(self.root, crate_root, ('crates/inner/build.rs',))}
        self.assertIn('crates/inner/build.rs', resolved,
                      'a nested member\'s target must resolve against the repository root')

    def test_a_nested_members_non_conventional_targets_are_audited(self):
        """Require ``build.rs`` and integration tests of a nested member to be read."""
        reported = {location for item, location in _shipped_items(self.root)}
        self.assertIn('crates/inner/build.rs:1:19', reported,
                      'a nested member\'s build script must reach the audit')
        self.assertIn('crates/inner/tests/probe.rs:1:16', reported,
                      'a nested member\'s integration test must reach the audit')


class ShippedCratesAreAudited(unittest.TestCase):
    """Require the check to pass against the repository as committed (VO-10).

    This is VO-10's positive half. Its negative half is the seeded-fixture
    assertion inside the same check, which is what makes an empty result mean
    something rather than merely being empty.
    """

    def test_workspace_members_report_no_trust_and_fixtures_stay_seeded(self):
        """Accept the committed repository and record one result."""
        context = ValidationContext(ROOT)
        check_trust_audit(context)
        self.assertEqual([row['check'] for row in context.results], ['trust-audit'],
                         'the check must record exactly one result')

    def test_fixture_corpus_still_reports_every_seeded_item(self):
        """Require the corpus to contain the trust the control names.

        Without this the seeded map could silently stop matching, and the check
        would be back to asserting emptiness with nothing to compare against.
        """
        reported = {entry.path: {item.item for item in entry.items}
                    for entry in audit_tree(ROOT, [CORPUS])}
        self.assertEqual(reported.get(CORPUS), SEEDED_ITEMS[CORPUS],
                         'the corpus must report exactly the items it seeds')

    def test_audit_tree_agrees_with_a_direct_scan_of_the_corpus(self):
        """Require the tree walk and a single-file scan to agree.

        The check reads items through :func:`audit_tree` and a record would be
        produced from the same walk, so a disagreement with the scanner itself
        would make every comparison fail for a reason nothing else covers.
        """
        walked = [item for entry in audit_tree(ROOT, [CORPUS]) if entry.path == CORPUS
                  for item in entry.items]
        self.assertEqual(walked, list(scan((ROOT / CORPUS).read_text(encoding='utf-8')).items),
                         'the tree walk must report the scanner\'s own items')


class BrokenScanners(unittest.TestCase):
    """Show that VO-10's check notices a scanner that stopped working.

    Each variant breaks one promise and is installed in place of the real
    scanner under the names the check imports. The point is not that the scanner
    is correct — the cases above cover that — but that the check's negative half
    fails when it is not.
    """

    def test_a_scanner_reporting_nothing_fails_the_seeded_fixtures(self):
        """Fail when the audit goes silent everywhere."""
        with _fixed_scanner(()):
            with self.assertRaises(AssertionError) as raised:
                check_trust_audit(ValidationContext(ROOT))
        self.assertIn('must report', str(raised.exception),
                      'a silent scanner must fail the non-vacuity control')

    def test_a_scanner_reporting_an_item_in_a_shipped_crate_fails(self):
        """Fail when a shipped crate reports trust."""
        with _fixed_scanner(('admit',)):
            with self.assertRaises(AssertionError) as raised:
                check_trust_audit(ValidationContext(ROOT))
        self.assertIn('shipped crates must contain no trust items', str(raised.exception),
                      'a shipped item must fail the positive half')


class _FixedScanner:
    """Stand in for the audit, reporting a fixed set of items for every source."""

    def __init__(self, names: tuple[str, ...]) -> None:
        """Record the item names this scanner reports for every file."""
        self._names = names

    def audit_tree(self, root, drivers):
        """Report the fixed items against every named driver."""
        del root
        return tuple(AuditedFile(driver, tuple(TrustItem(name, 1, 1) for name in self._names))
                     for driver in drivers)

    def items_of(self, files):
        """Render the fixed items in the schema's shape."""
        return tuple({'item': item.item, 'location': f'{entry.path}:1:1', 'covered_by': None}
                     for entry in files for item in entry.items)


class _Patch:
    """Install one scanner in place of the check's own, for the body of a case."""

    def __init__(self, scanner: _FixedScanner) -> None:
        """Record the replacement scanner."""
        self._scanner = scanner

    def __enter__(self):
        """Replace the names the check imports, and record the originals."""
        import docs_validation.trust_audit_check as module
        self._originals = module.audit_tree, module.items_of
        module.audit_tree, module.items_of = self._scanner.audit_tree, self._scanner.items_of
        return self

    def __exit__(self, *_):
        """Restore the real scanner."""
        import docs_validation.trust_audit_check as module
        module.audit_tree, module.items_of = self._originals
        return False


def _fixed_scanner(names: tuple[str, ...]) -> _Patch:
    """Return a context manager installing a scanner that reports ``names``."""
    return _Patch(_FixedScanner(names))
