"""Bind every committed verifier record to the sources it claims to describe.

A digest map is only evidence while it still matches the tree. Two directions
are checked here: a record must carry digests for the inputs its verdict
depends on, and every digest it does carry must still match the working tree.
The second direction is what makes a stale record fail loudly instead of
quietly describing a tree that no longer exists.

The hosted verifier-free record gets its own requirement, because nothing in
the generator writes it: the workflow uploads an artifact and a human promotes
it, so only this suite forces it to name the staged inputs and the run that
produced it.

For example::

    python3 -m unittest test_verifier_record_digests
"""

from __future__ import annotations

import hashlib
import json
import unittest

from verifier_probe_loader import ROOT
from verifier_records import committed_record_documents

HOSTED_RECORD = (
    'tools/verifier-fixtures/verus-wiring-probe/verifier-free-hosted.json'
)


class SourceDigestTests(unittest.TestCase):
    """Require every digest a record carries to describe the current tree."""

    def test_recorded_source_digests_match_the_working_tree(self) -> None:
        """Fail when a recorded source changed after its record was written."""
        checked = 0
        for record_path, record in committed_record_documents():
            for relative, expected in record.get('source_digests', {}).items():
                with self.subTest(record=str(record_path), source=relative):
                    actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                    recipe = (
                        'make verus-probe'
                        if 'verus-wiring-probe' in str(record_path)
                        else 'make kani-log-corpus'
                    )
                    self.assertEqual(
                        actual,
                        expected,
                        f'{relative} changed after {record_path.name} recorded it; '
                        f'regenerate the record with `{recipe}`',
                    )
                    checked += 1

        self.assertGreater(
            checked, 0, 'a committed record must bind at least one source'
        )


class HostedRecordTests(unittest.TestCase):
    """Require the hosted observation to bind what it built and where."""

    def setUp(self) -> None:
        """Load the promoted artifact once for every case."""
        self.record = json.loads((ROOT / HOSTED_RECORD).read_text(encoding='utf-8'))

    def test_the_hosted_record_binds_its_staged_inputs(self) -> None:
        """A hosted pass must name the inputs it actually built.

        The record is promoted by hand from a workflow artifact, so nothing in
        the generator forces it to carry digests. Without them it is a claim
        about an unrecorded tree: the toolchain, linker, and fixture sources
        could have changed after the run and the record would not notice.
        """
        digests = self.record.get('source_digests', {})

        self.assertTrue(digests, 'the hosted record must bind the staged inputs it built')
        for relative in (
            'rust-toolchain.toml',
            'tools/verifier-fixtures/verus-wiring-probe/Cargo.lock',
            'scripts/native-clang-linker.sh',
            '.cargo/config.toml',
        ):
            self.assertIn(
                relative,
                digests,
                f'{relative} changes what was built, so the record must bind it',
            )

    def test_the_hosted_record_binds_its_run_identity(self) -> None:
        """A passing record that names no run cannot be traced back to one."""
        provenance = self.record['provenance']

        for field in (
            'workflow',
            'job',
            'run_id',
            'run_url',
            'head_sha',
            'runner_image',
            'collected',
        ):
            self.assertTrue(
                provenance.get(field), f'the hosted record must name its {field}'
            )
        self.assertRegex(
            provenance['head_sha'],
            r'^[0-9a-f]{40}$',
            'the hosted record must bind a full commit, not a short one',
        )

    def test_the_hosted_record_reports_the_passing_status(self) -> None:
        """A record that did not pass must not be committed as evidence."""
        self.assertEqual(
            self.record['status'],
            'pass',
            'the promoted hosted observation must be a passing run',
        )


if __name__ == '__main__':
    unittest.main()
