"""Prove the toolchain record is bound to its sources and its evidence (VO-7, VO-8).

Each test here exists to show the checker would *fail*. A checker whose
assertions can never fire is indistinguishable from one that always passes, so
every case below breaks exactly one promise the record makes and requires the
named failure. The positive case at the end keeps the pair honest: the same
checker must accept the record the repository actually commits.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.toolchain_profiles import (
    RECORD, SCHEMA, check_toolchain_profiles,
)

ROOT = Path(__file__).resolve().parents[2]


def record_at(root: Path) -> dict:
    """Read the toolchain record from whichever root a test is inspecting."""
    return json.loads((root / RECORD).read_text(encoding='utf-8'))


def write_record(root: Path, record: dict) -> None:
    """Replace the record under a scratch root so the checker reads the edit."""
    (root / RECORD).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')


class ScratchTree(unittest.TestCase):
    """Provide a scratch copy of the inputs a toolchain check reads.

    Copying the files the record names, rather than the whole checkout, keeps
    each case too fast to serialise and small enough that a reader can see what
    the check actually consults.
    """

    def setUp(self) -> None:
        """Copy the toolchain inputs the check reads into a scratch directory."""
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        record = record_at(ROOT)
        sources = {site for pin in record['pins'].values() for site in pin['sites']}
        for relative in sorted({RECORD, SCHEMA, *sources}):
            source = ROOT / relative
            if not source.is_file():
                continue
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        # The sweep reads the facets' owning files through bespoke readers, so
        # copy those too rather than assembling them per test.
        for relative in ('Cargo.toml', 'rust-toolchain.toml',
                         'tools/rust-prover-tools/REF', 'tools/kani/VERSION',
                         'tools/verus/VERSION'):
            target = self.root / relative
            if target.is_file():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        fixtures = ROOT / 'tools/verifier-fixtures/verus-wiring-probe'
        shutil.copytree(fixtures, self.root / 'tools/verifier-fixtures/verus-wiring-probe',
                        dirs_exist_ok=True)
        self.tracked = sorted(
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob('*') if path.is_file()
        )

    def tearDown(self) -> None:
        """Remove the scratch directory and everything copied into it."""
        self._directory.cleanup()

    def check(self, tracked: list[str] | None = None) -> None:
        """Run the checker against the scratch root with an explicit file list."""
        check_toolchain_profiles(
            ValidationContext(self.root), self.tracked if tracked is None else tracked,
        )

    def assert_fails(self, fragment: str, tracked: list[str] | None = None) -> None:
        """Require the checker to fail with a message naming the broken promise."""
        with self.assertRaises(AssertionError) as raised:
            self.check(tracked)
        self.assertIn(fragment, str(raised.exception),
                      f'the failure must name {fragment!r}; got {raised.exception}')


class SourcedPins(ScratchTree):
    """VO-7: a pin re-derived from its owning file must match the record."""

    def test_repository_channel_drift_is_caught(self):
        """Change `rust-toolchain.toml` alone and require the disagreement."""
        channel = (self.root / 'rust-toolchain.toml').read_text(encoding='utf-8')
        (self.root / 'rust-toolchain.toml').write_text(
            channel.replace('nightly-2026-11-06', 'nightly-2026-09-01'), encoding='utf-8',
        )
        self.assert_fails('repository_channel')

    def test_kani_release_drift_is_caught(self):
        """Change Kani's VERSION file alone and require the disagreement."""
        (self.root / 'tools/kani/VERSION').write_text('0.68.0\n', encoding='utf-8')
        self.assert_fails('kani_release')

    def test_verus_release_drift_is_caught(self):
        """Change Verus's VERSION file alone and require the disagreement."""
        (self.root / 'tools/verus/VERSION').write_text('0.2026.10.01.deadbee\n', encoding='utf-8')
        self.assert_fails('verus_release')

    def test_prover_tools_ref_drift_is_caught(self):
        """Change the prover-tools REF alone and require the disagreement."""
        ref = self.root / 'tools/rust-prover-tools/REF'
        text = ref.read_text(encoding='utf-8')
        original = next(line.split(':', 1)[1].strip()
                        for line in text.splitlines() if line.startswith('ref:'))
        ref.write_text(text.replace(original, 'f' * 40), encoding='utf-8')
        self.assert_fails('prover_tools_ref')

    def test_polars_requirement_drift_is_caught(self):
        """Change the facade's Polars requirement alone and require the disagreement."""
        manifest = (self.root / 'Cargo.toml').read_text(encoding='utf-8')
        (self.root / 'Cargo.toml').write_text(
            manifest.replace('version = "0.55.2"', 'version = "0.56.0"', 1), encoding='utf-8',
        )
        self.assert_fails('polars_release')

    def test_vstd_disagreement_between_fixtures_is_caught(self):
        """Move one fixture manifest's vstd alone and require the disagreement.

        The three manifests are meant to select one vstd; picking the most
        common value would silently accept a half-migrated fixture set.
        """
        manifest = self.root / 'tools/verifier-fixtures/verus-wiring-probe/companion/Cargo.toml'
        text = manifest.read_text(encoding='utf-8')
        manifest.write_text(text.replace('0.0.0-2026-09-06-0133', '0.0.0-2026-10-01-0000'),
                            encoding='utf-8')
        self.assert_fails('vstd')

    def test_cited_site_that_no_longer_names_the_pin_is_caught(self):
        """Drop the value from one cited site and require the citation check.

        This is the drift the record's own site list is supposed to prevent:
        the record keeps promising a site long after the site moved on.
        """
        site = self.root / 'tests/prover_tools_contract.rs'
        self.assertTrue(site.is_file(), 'the fixture tree must contain the cited site')
        site.write_text(site.read_text(encoding='utf-8').replace('0.2026.09.06.8dea4a2', 'X'),
                        encoding='utf-8')
        self.assert_fails('verus_release cites a site that does not contain')

    def test_a_pin_with_no_reader_is_still_bound_to_its_sites(self):
        """Require the citation check to cover pins no owning file can re-derive.

        Six of the twelve pins have a reader; the rest are known only through
        the sites the record names for them. A sweep that visited the reader's
        pins alone would report a clean record while the other six had drifted,
        which is the failure this case pins down.
        """
        record = record_at(self.root)
        self.assertNotIn('kani_toolchain',
                         {'repository_channel', 'kani_release', 'verus_release',
                          'prover_tools_ref', 'verus_vstd', 'polars_release'},
                         'the case is meaningless if the pin it edits has a reader')
        site = self.root / 'tests/support/prover_tools_probe.rs'
        self.assertTrue(site.is_file(), 'the fixture tree must contain the cited site')
        needle = record['pins']['kani_toolchain']['value']
        site.write_text(site.read_text(encoding='utf-8').replace(needle, 'X'),
                        encoding='utf-8')
        self.assert_fails('pin kani_toolchain cites a site that does not contain')


class PinSweep(ScratchTree):
    """VO-7: a pin may not live in a file the record does not name."""

    def test_unlisted_site_is_caught(self):
        """Add a file naming a pin and require the sweep to report it."""
        stray = self.root / 'tests/stray_pin.txt'
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text('kani 0.67.0\n', encoding='utf-8')
        self.assert_fails('tests/stray_pin.txt names pin kani_release',
                          [*self.tracked, 'tests/stray_pin.txt'])

    def test_listed_site_passes_the_sweep(self):
        """List the same file in the record and require the sweep to accept it."""
        stray = self.root / 'tests/stray_pin.txt'
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text('kani 0.67.0\n', encoding='utf-8')
        record = record_at(self.root)
        record['pins']['kani_release']['sites'].append('tests/stray_pin.txt')
        write_record(self.root, record)
        self.check([*self.tracked, 'tests/stray_pin.txt'])

    def test_capture_directory_is_not_a_site(self):
        """A captured log restates a pin without setting it, so it is skipped."""
        capture = self.root / 'scripts/tests/fixtures/kani_logs/captured.log'
        capture.parent.mkdir(parents=True, exist_ok=True)
        capture.write_text('kani 0.67.0\n', encoding='utf-8')
        self.check([*self.tracked, 'scripts/tests/fixtures/kani_logs/captured.log'])

    def test_documentation_is_not_a_site(self):
        """Prose restates pins on purpose, so a Markdown mention is skipped."""
        page = self.root / 'docs/mention.md'
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text('Kani 0.67.0\n', encoding='utf-8')
        self.check([*self.tracked, 'docs/mention.md'])

    def test_sweep_reads_the_live_tree_by_default(self):
        """Prove production runs the real sweep, not a truncated list.

        The default argument is what the composition root relies on, and every
        other case here supplies its own list, so none of them exercises it. A
        default that enumerated only the record's own sites would still pass
        them all while catching nothing. This therefore calls the checker with
        no ``tracked`` argument and requires a file the record does not name to
        be found through the enumeration the sweep performs itself.
        """
        stray = self.root / 'tests/stray_pin.txt'
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text('kani 0.67.0\n', encoding='utf-8')
        enumerated = [*self.tracked, 'tests/stray_pin.txt']
        with patch('docs_validation.revision_reader.tracked_paths',
                   return_value=enumerated) as live_tree:
            with self.assertRaises(AssertionError) as raised:
                check_toolchain_profiles(ValidationContext(self.root))
        live_tree.assert_called_once_with(self.root)
        self.assertIn('tests/stray_pin.txt names pin kani_release', str(raised.exception),
                      'the default sweep must read the enumeration rather than the record')


class CapabilityEvidence(ScratchTree):
    """VO-8: a status that claims an observation must cite a matching log."""

    def _claim_tested(self, path: str) -> None:
        """Mark PC01 tested with the given evidence path."""
        record = record_at(self.root)
        record['capabilities'][0]['status'] = 'tested'
        record['capabilities'][0]['evidence'] = {'path': path, 'sha256': '0' * 64}
        write_record(self.root, record)

    def test_tested_capability_without_evidence_is_rejected(self):
        """A claimed observation with no log must fail the schema itself."""
        from jsonschema import ValidationError

        record = record_at(self.root)
        record['capabilities'][0]['status'] = 'tested'
        write_record(self.root, record)
        with self.assertRaises(ValidationError) as raised:
            self.check()
        self.assertIn('evidence', str(raised.exception),
                      'the schema must require evidence once a status claims an observation')

    def test_tested_capability_with_missing_log_is_caught(self):
        """A cited log that is not committed must fail the evidence check."""
        self._claim_tested('spec/measurements/absent.log')
        self.assert_fails('cites missing evidence')

    def test_tested_capability_with_wrong_digest_is_caught(self):
        """A committed log whose digest disagrees must fail the evidence check."""
        log = self.root / 'spec/measurements/pc01.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text('the probe ran\n', encoding='utf-8')
        self._claim_tested('spec/measurements/pc01.log')
        self.assert_fails('evidence digest does not match')

    def test_tested_capability_with_matching_digest_passes(self):
        """A committed log with the recorded digest must be accepted."""
        import hashlib

        log = self.root / 'spec/measurements/pc01.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text('the probe ran\n', encoding='utf-8')
        record = record_at(self.root)
        record['capabilities'][0]['status'] = 'inconclusive'
        record['capabilities'][0]['evidence'] = {
            'path': 'spec/measurements/pc01.log',
            'sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
        }
        write_record(self.root, record)
        self.check()


class RepositoryRecord(ScratchTree):
    """The committed record must satisfy the checker it ships with."""

    def test_committed_record_is_accepted(self):
        """Guard against a test suite that only ever exercises broken inputs."""
        self.check()

    def test_duplicate_profile_id_is_caught(self):
        """Two profiles with one ID would let a gate run the wrong feature set."""
        record = record_at(self.root)
        record['profiles'][1]['id'] = record['profiles'][0]['id']
        write_record(self.root, record)
        self.assert_fails('Duplicate profile ID')

    def test_two_ordinary_toolchains_are_caught(self):
        """The record answers Q3 by naming exactly one ordinary build toolchain."""
        record = record_at(self.root)
        record['supported_toolchain_set'][0]['ordinary'] = False
        record['supported_toolchain_set'][1]['ordinary'] = True
        record['supported_toolchain_set'][2]['ordinary'] = True
        write_record(self.root, record)
        self.assert_fails('Exactly one supported toolchain')


if __name__ == '__main__':
    unittest.main()
