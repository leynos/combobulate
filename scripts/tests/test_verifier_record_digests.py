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

from verifier_probe_loader import ROOT, load_verifier_free_probe
from verifier_records import committed_record_documents

# The staged set is the staging function's own answer, so the record can only
# be compared with what the generator copies rather than a second list here.
staged_sources = load_verifier_free_probe().staged_sources

HOSTED_RECORD = (
    'tools/verifier-fixtures/verus-wiring-probe/verifier-free-hosted.json'
)


def unbound_staged_inputs(digests: dict[str, str]) -> list[str]:
    """Return the staged inputs a record's digest map does not cover.

    Comparing key sets in both directions is the point: a missing key hides an
    input the build read, and an extra key claims one it never did. A record
    that names only the inputs a reviewer thinks of would otherwise pass.

    Examples
    --------
    A record binding nothing leaves every staged input unbound::

        unbound_staged_inputs({})
        # ['rust-toolchain.toml', ...]
    """
    staged = {str(path.relative_to(ROOT)) for path in staged_sources()}
    return sorted(staged - set(digests))


def unstaged_recorded_inputs(digests: dict[str, str]) -> list[str]:
    """Return the recorded inputs the verifier-free build never stages."""
    staged = {str(path.relative_to(ROOT)) for path in staged_sources()}
    return sorted(set(digests) - staged)


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
        self.assertTrue(
            self.record.get('source_digests', {}),
            'the hosted record must bind the staged inputs it built',
        )

    def test_the_hosted_record_binds_every_staged_input(self) -> None:
        """The record must cover the whole staged set, not a sample of it.

        A hand-promoted record could name the four inputs a reviewer thinks of
        and silently omit the rest. Every file ``staged_sources`` copies
        changes what the container built, so the recorded key set has to equal
        the staged set in both directions: a missing key hides an input, and an
        extra key would bind a file the build never read.
        """
        digests = self.record.get('source_digests', {})

        self.assertEqual(
            unbound_staged_inputs(digests),
            [],
            'every staged input changes what was built, so the record must bind it',
        )
        self.assertEqual(
            unstaged_recorded_inputs(digests),
            [],
            'the record must not bind files the verifier-free build never stages',
        )

    def test_a_record_missing_a_staged_input_is_rejected(self) -> None:
        """The comparison above must fail when one staged input is dropped.

        Guarding the guard: comparing two sets that both came from the record
        would pass whatever it held. Dropping one staged key has to be
        detected by the same predicate the real case uses, so the
        missing-entry direction is proven rather than assumed.
        """
        digests = dict(self.record['source_digests'])
        dropped = min(digests)
        self.assertIn(
            dropped,
            {str(path.relative_to(ROOT)) for path in staged_sources()},
            'the case needs a staged key, which the real record already covers',
        )
        del digests[dropped]

        self.assertEqual(
            unbound_staged_inputs(digests),
            [dropped],
            'dropping a staged input must leave exactly that input unbound',
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
