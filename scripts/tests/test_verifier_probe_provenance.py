"""Keep recorded verifier provenance free of host-specific paths.

A committed command that names ``/home/<user>`` publishes the account name and
the worktree layout, and it cannot be reproduced on another machine. The probe
still executes the real argument vector; only the recorded copy is rewritten.
"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from verifier_probe_loader import (
    ROOT,
    load_probe_provenance,
    load_verifier_probe_support,
)
from verifier_records import (
    committed_record_documents,
    committed_records,
    publishes_host_detail,
    record_documents,
    recorded_paths,
)


class CommittedRecordTests(unittest.TestCase):
    """Keep every committed record portable, whoever captured it.

    ``portable_argument`` governs new captures. A record captured before that
    rule still carries the runner's account path, and because the digest binds
    the captured log rather than the metadata, such a record is rewritten in
    place instead of being recaptured.
    """

    def test_records_are_discovered(self) -> None:
        """The scan must reach the committed records, not an empty directory."""
        records = committed_records()

        scanned = [path for path, _ in records]

        self.assertIn(
            ROOT / 'tools/verifier-fixtures/verus-wiring-probe/verifier-free-hosted.json',
            scanned,
            'the hosted verifier-free record must be covered by the portability scan',
        )
        self.assertIn(
            ROOT / 'scripts/tests/fixtures/kani_logs/provenance.json',
            scanned,
            'the Kani provenance record must be covered by the portability scan',
        )
        self.assertTrue(
            any(arguments for _, arguments in records),
            'the portability scan must find at least one recorded command',
        )

    def test_solver_paths_are_scanned(self) -> None:
        """A recorded solver path follows the same portability rule."""
        paths = recorded_paths({'z3': '/home/runner/.cache/uv/bin/z3'})

        self.assertEqual(
            paths,
            ['/home/runner/.cache/uv/bin/z3'],
            'the solver path must be collected with the command arguments',
        )
        self.assertTrue(
            any(publishes_host_detail(path) for path in paths),
            'a solver path naming an account home must fail the portability scan',
        )

    def test_committed_paths_publish_no_host_paths(self) -> None:
        """No committed path may reveal the account or worktree that ran it."""
        offenders = [
            f'{path.relative_to(ROOT)}: {recorded}'
            for path, recorded_paths in committed_records()
            for recorded in recorded_paths
            if publishes_host_detail(recorded)
        ]

        self.assertEqual(
            offenders,
            [],
            'recorded paths must replace host roots with `<repo>` and `~`',
        )

    def test_build_output_is_not_read_as_a_record(self) -> None:
        """A fixture crate's Cargo output must not be parsed as provenance."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'provenance.json').write_text('{"source_digests": {}}', encoding='utf-8')
            build = root / 'candidate/target/debug'
            build.mkdir(parents=True)
            (build / 'metadata.json').write_text('[]', encoding='utf-8')

            documents = record_documents(root)

        self.assertEqual(
            [path.name for path, _ in documents],
            ['provenance.json'],
            'a Cargo target directory must stay out of the record scan',
        )

class VerusProvenanceTests(unittest.TestCase):
    """Record the solver without its per-user cache path."""

    def test_solver_path_is_recorded_portably(self) -> None:
        """A uv cache path must not reach the committed record."""
        module = load_probe_provenance()
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            solver = home / '.cache/uv/archive-v0/bin/z3'
            solver.parent.mkdir(parents=True)
            solver.write_text('solver')
            record_path = home / 'provenance.json'

            with patch.object(Path, 'home', return_value=home):
                module._write_verus_provenance(
                    record_path,
                    '0.2026.09.06.8dea4a2',
                    solver,
                    'Z3 version 4.16.0 - 64 bit',
                    None,
                    [],
                )

            record = json.loads(record_path.read_text(encoding='utf-8'))

        self.assertEqual(
            record['z3'],
            '~/.cache/uv/archive-v0/bin/z3',
            'the solver path must be recorded relative to the home directory',
        )
        self.assertIsNone(
            record['z3_distribution'],
            'an explicit solver must not be attributed to the pinned distribution',
        )

    def test_pinned_distribution_is_recorded_when_its_resolver_supplied_it(self) -> None:
        """The default route must keep naming the distribution behind the pin."""
        module = load_probe_provenance()
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            solver = home / 'z3'
            solver.write_text('solver')
            record_path = home / 'provenance.json'

            with patch.object(Path, 'home', return_value=home):
                module._write_verus_provenance(
                    record_path,
                    '0.2026.09.06.8dea4a2',
                    solver,
                    'Z3 version 4.16.0 - 64 bit',
                    module.Z3_DISTRIBUTION,
                    [],
                )

            record = json.loads(record_path.read_text(encoding='utf-8'))

        self.assertEqual(
            record['z3_distribution'],
            'z3-solver==4.16.0.0',
            'the pinned resolver must remain attributed to its distribution',
        )


class VerusSourceBindingTests(unittest.TestCase):
    """Require the Verus record to bind every source a verdict depends on."""

    _REQUIRED = frozenset({
        'tools/verifier-fixtures/verus-wiring-probe/macro.rs',
        'tools/verifier-fixtures/verus-wiring-probe/attributes.rs',
        'tools/verifier-fixtures/verus-wiring-probe/companion.rs',
        'tools/verifier-fixtures/verus-wiring-probe/single-root.rs',
        'tools/verifier-fixtures/verus-wiring-probe/production.rs',
        'tools/verifier-fixtures/verus-wiring-probe/Cargo.toml',
        'tools/verifier-fixtures/verus-wiring-probe/Cargo.lock',
        'tools/verifier-fixtures/verus-wiring-probe/macro/Cargo.toml',
        'tools/verifier-fixtures/verus-wiring-probe/attributes/Cargo.toml',
        'tools/verifier-fixtures/verus-wiring-probe/companion/Cargo.toml',
        'tools/verifier-fixtures/verus-wiring-probe/production/Cargo.toml',
        'scripts/run_verifier_probes.py',
        'scripts/verus_probe.py',
        'scripts/probe_provenance.py',
        'scripts/verifier_probe_support.py',
    })

    def test_every_provenance_record_binds_sources(self) -> None:
        """A record without source digests must not pass as bound evidence."""
        records = [
            (path, record)
            for path, record in committed_record_documents()
            if path.name == 'provenance.json'
        ]

        self.assertTrue(records, 'the scan must find committed provenance records')
        for path, record in records:
            with self.subTest(record=str(path)):
                self.assertTrue(
                    record.get('source_digests'),
                    f'{path} must bind the sources behind its observations',
                )

    def test_verus_record_binds_fixtures_manifests_and_generators(self) -> None:
        """A Verus verdict must name every input that can change it."""
        path = ROOT / 'tools/verifier-fixtures/verus-wiring-probe/provenance.json'
        record = json.loads(path.read_text(encoding='utf-8'))

        missing = sorted(self._REQUIRED - record['source_digests'].keys())

        self.assertEqual(
            missing,
            [],
            'the Verus record must bind its fixture sources, manifests, lockfile, '
            'and generating scripts',
        )
