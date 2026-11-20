"""Keep the committed kernel proof record reproducible and host-free.

The record is a development artefact (DL-1), but it still has to mean what it
says: the digests must bind the bytes a reader can check, the identity tuple
must describe the operation the source declares, and no observation may
publish a worktree path. These tests read the committed record rather than a
fresh one, so an edit to the driver that is not followed by a re-run fails
here.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from verus_kernel_fixtures import RECORD, ROOT, SCRIPTS, load, load_driver

class RecordTests(unittest.TestCase):
    """Keep the committed record reproducible and free of host paths."""

    def setUp(self) -> None:
        """Load the driver, its record module and the identity module per test."""
        self.driver = load_driver()
        self.record = load('kernel_record', SCRIPTS / 'kernel_record.py')
        self.identity = load(
            'verus_kernel_identity', SCRIPTS / 'verus_kernel_identity.py'
        )

    def _record(self) -> dict:
        """Read the committed record, which every assertion here inspects."""
        return json.loads(RECORD.read_text(encoding='utf-8'))

    def test_portable_text_removes_both_roots(self) -> None:
        """Both the repository root and the home directory must be rewritten."""
        text = f'{ROOT}/crates and {Path.home()}/cache'

        rewritten = self.record.portable_text(text)

        self.assertEqual(rewritten, '<repo>/crates and ~/cache')

    def test_portable_log_drops_the_helper_install_line(self) -> None:
        """A cache-warmth report must not reach a committed log.

        The helper prints the package count and duration of an environment it
        has just built, in ANSI styling. Both values follow the cache rather
        than the proof, so a log that kept them would differ between a cold and
        a warm run and make the record irreproducible.
        """
        styled = '\x1b[2mInstalled \x1b[1m10 packages\x1b[0m \x1b[2min 27ms\x1b[0m\n'
        log = f'{styled}verification results:: 20 verified, 0 errors\n'

        cleaned = self.record.portable_log(log)

        self.assertEqual(cleaned, 'verification results:: 20 verified, 0 errors\n')

    def test_portable_log_keeps_a_verifier_line_that_mentions_installing(self) -> None:
        """Only the helper's exact bootstrap line is noise.

        A verifier diagnostic that happens to discuss installation must survive,
        or the rule would silently discard evidence.
        """
        diagnostic = 'error: a package installed by the solver is missing\n'

        self.assertEqual(self.record.portable_log(diagnostic), diagnostic)

    def test_portable_log_removes_a_host_path(self) -> None:
        """The log's host paths must be rewritten, not merely tolerated."""
        log = f'  --> {ROOT}/kernel.rs:10:5\n'

        self.assertEqual(self.record.portable_log(log), '  --> <repo>/kernel.rs:10:5\n')

    def test_the_committed_record_carries_no_host_path(self) -> None:
        """A committed observation must not publish a worktree or account name."""
        text = RECORD.read_text(encoding='utf-8')

        self.assertNotIn(str(ROOT), text)
        self.assertNotIn(str(Path.home()), text)

    def test_every_committed_log_matches_its_digest(self) -> None:
        """A digest must bind the exact bytes a reader can check."""
        for observation in self._record()['observations']:
            with self.subTest(candidate=observation['candidate']):
                log = ROOT / observation['log']
                digest = hashlib.sha256(log.read_bytes()).hexdigest()
                self.assertEqual(digest, observation['sha256'])

    def test_the_record_binds_the_verdict_rules_it_was_decided_by(self) -> None:
        """Splitting the rules out must not leave them outside the record.

        The digests bind the scripts that produced these observations. A driver
        whose rules moved to a sibling module still has to name that module, or
        a reader could re-run the recorded commands against different rules.
        """
        digests = self._record()['source_digests']

        self.assertIn('scripts/verus_kernel.py', digests)
        self.assertIn('scripts/verus_kernel_verdicts.py', digests)
        self.assertIn('scripts/verus_kernel_diagnostic.py', digests)

    def test_the_record_binds_the_mutation_it_was_proved_by(self) -> None:
        """The wrap mutant is built by a module, so that module is a rule too.

        ``verus_kernel_body`` decides which two sites the wrap root mutates and
        what replaces them. An unbound mutation would let a reader re-run the
        recorded command against a different body and still call it the same
        evidence.
        """
        self.assertIn('scripts/verus_kernel_body.py', self._record()['source_digests'])

    def test_the_record_binds_the_digest_rule_it_was_computed_by(self) -> None:
        """The structural digest is a rule too, so its source must be bound."""
        self.assertIn('scripts/kernel_record.py', self._record()['source_digests'])

    def test_every_source_digest_still_describes_the_committed_file(self) -> None:
        """A bound digest must be recomputable from the source beside it.

        Binding a source is only useful if the stored digest still matches it:
        an entry left behind by an edit names a file no reader can check, and
        nothing else in the record would show the difference. A driver edit
        that is not followed by ``make verus-kernel`` fails here.
        """
        stale = {
            relative: recorded
            for relative, recorded in self._record()['source_digests'].items()
            if self.record.structural_digest(ROOT / relative) != recorded
        }

        self.assertEqual(
            stale,
            {},
            f'run `make verus-kernel` to rebind edited sources: {sorted(stale)}',
        )

    def test_the_record_hands_admission_to_the_proof_profile(self) -> None:
        """The observations must name PF05 as the admitting component."""
        admission = self._record()['admission']

        self.assertIn('PF05.proof@2.3.5', admission)

    def test_the_record_states_the_identity_it_is_about(self) -> None:
        """DL-14's tuple must name the operation, not just carry its digests.

        The digests are already in the record unlabelled, so a reader could
        not tell which catalogue entry, dtype or policy they verify. Each
        component is checked against the committed value, and the executable
        and specification entries must carry the same digests the record
        holds for those files, or the tuple would name files it does not bind.
        """
        record = self._record()
        tuple_ = record['identity']
        digests = record['source_digests']

        self.assertEqual(tuple_['catalogue_id'], 'V001')
        self.assertEqual(tuple_['operation'], {'name': 'add', 'catalogue_id': 'V001'})
        self.assertEqual(tuple_['dtype'], 'I64')
        self.assertEqual(
            tuple_['symbol'], 'combobulate_kernel::elementwise_add::add_i64_into'
        )
        self.assertEqual(tuple_['semantic_policy'], 'checked-i64')
        self.assertEqual(tuple_['executable']['digest'], digests[tuple_['executable']['path']])
        self.assertEqual(
            tuple_['specification']['digest'], digests[tuple_['specification']['path']]
        )

    def test_the_record_binds_the_identity_module(self) -> None:
        """The tuple's own source must be in the digests, as the rules' is."""
        self.assertIn(
            'scripts/verus_kernel_identity.py', self._record()['source_digests']
        )

    def test_the_committed_tuple_is_what_the_module_composes(self) -> None:
        """The record must be the module's output, not a stale copy of it.

        Every other assertion here reads the committed record, so a constant
        edited in ``verus_kernel_identity.py`` without a re-run would leave
        the record naming the operation the source no longer describes, and
        nothing would fail. Composing the tuple again from the digests the
        record already binds is what makes the record reproducible rather
        than merely well-formed. The digests are passed in so this case does
        not depend on an unrelated source edit invalidating the record.
        """
        record = self._record()
        tuple_ = record['identity']

        self.assertEqual(
            self.identity.identity(
                tuple_['executable']['digest'], tuple_['specification']['digest']
            ),
            tuple_,
        )

    def test_the_identity_names_what_the_rust_source_declares(self) -> None:
        """The tuple is a claim about the code, so it must match it.

        A catalogue id or a symbol that drifts from the shipped source would
        make the record a statement about an operation that no longer exists.
        The check reads the two declarations rather than trusting the
        constants, so renaming one without the other fails here.
        """
        source = (ROOT / 'crates/combobulate-kernel/src/elementwise_add.rs').read_text(
            encoding='utf-8'
        )
        facade = (ROOT / 'src/expr/mod.rs').read_text(encoding='utf-8')
        tuple_ = self._record()['identity']

        self.assertIn(f'fn {tuple_["operation"]["name"]}_i64_into(', source)
        self.assertIn(f'name: "{tuple_["operation"]["name"]}"', facade)
        self.assertIn(f'catalogue_id: "{tuple_["catalogue_id"]}"', facade)

    def test_every_mutant_is_recorded_once(self) -> None:
        """One observation per mutant, plus the positive root and the wrap copy."""
        candidates = [
            observation['candidate']
            for observation in self._record()['observations']
        ]

        self.assertEqual(candidates.count('positive'), 1)
        self.assertEqual(candidates.count('wrap'), 1)
        for name in self.driver.MUTANTS:
            self.assertEqual(candidates.count(name), 1, name)
