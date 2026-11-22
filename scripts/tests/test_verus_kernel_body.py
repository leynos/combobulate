"""Qualify the body-tier mutant's verdict without running a solver.

M-wrap copies the shipped body into a scratch directory and replaces the
overflow test with a wrapping one. The rule that decides whether the resulting
log is that mutant's rejection is its own: the wrap root states no clauses of
its own, so the obligations it may fail are the mutated body's annotations, not
the postconditions the seeded wrappers fail.

These tests belong beside the other verdict tests but in their own module,
because the two tiers admit different failure sets and reading them side by side
would invite reusing one tier's permitted set for the other.

The loader that stubs the driver's module-scope imports lives in
:mod:`verus_kernel_fixtures`, so this file states what the rule must decide.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from verus_kernel_fixtures import ROOT, SUMMARY, load_driver


class BodyMutantTests(unittest.TestCase):
    """Require the wrapping body to fail a loop invariant, not something else."""

    def setUp(self) -> None:
        """Load the verdict rules and the body they qualify once per test."""
        self.driver = load_driver()
        self.invariant = self._invariant_line()

    def _invariant_line(self) -> int:
        """Return the line of the scan loop's invariant in the shipped body."""
        lines = self.driver.PRODUCTION.read_text(encoding='utf-8').splitlines()
        return next(
            index
            for index, text in enumerate(lines, start=1)
            if 'invariant' in text
        )

    def _assertion_line(self) -> int:
        """Return the line of the scan pass's own assertion."""
        lines = self.driver.PRODUCTION.read_text(encoding='utf-8').splitlines()
        return next(
            index
            for index, text in enumerate(lines, start=1)
            if 'assert(!in_range_at' in text
        )

    def test_a_loop_invariant_failure_qualifies(self) -> None:
        """An invariant failure with a non-zero error count is the verdict."""
        log = (
            'error: invariant not satisfied at loop head\n'
            f'  --> {self.driver.WRAP_BODY}:{self.invariant}:13\n'
            'error: assertion failed\n'
            f'  --> {self.driver.WRAP_BODY}:{self._assertion_line()}:29\n'
            'verification results:: 14 verified, 2 errors\n'
        )
        verdict = self.driver._qualify_body(log, 1, self.driver.WRAP_BODY)

        self.assertEqual(verdict['clause'], 'loop-invariant')

    def test_a_verified_body_is_rejected(self) -> None:
        """A body that verifies is not a rejected mutant."""
        with self.assertRaisesRegex(RuntimeError, 'must not verify'):
            self.driver._qualify_body(SUMMARY, 0, self.driver.WRAP_BODY)

    def test_a_postcondition_only_failure_is_rejected(self) -> None:
        """Some other obligation must not stand in for the loop invariant.

        The wrap root states no clauses of its own, so a postcondition failure
        is not an obligation the body tier can owe. It is rejected as
        disqualifying rather than merely as "no invariant present", which is the
        stronger of the two messages and the accurate one.
        """
        log = (
            'error: postcondition not satisfied\n'
            f'  --> {self.driver.WRAP_BODY}:{self.invariant}:13\n'
            'verification results:: 0 verified, 1 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'disqualifying error'):
            self.driver._qualify_body(log, 1, self.driver.WRAP_BODY)

    def test_a_duplicated_invariant_with_one_location_is_rejected(self) -> None:
        """One located failure must not account for two reported failures.

        Verus can report the same obligation twice, once with a location and
        once without. Comparing error text alone treats the second as
        explained; it is a separate diagnostic that could have failed anywhere.
        """
        log = (
            'error: invariant not satisfied at end of loop body\n'
            f'  --> {self.driver.WRAP_BODY}:{self.invariant}:13\n'
            'error: invariant not satisfied at end of loop body\n'
            'verification results:: 14 verified, 2 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'must all be located in the body'):
            self.driver._qualify_body(log, 1, self.driver.WRAP_BODY)

    def test_a_same_named_body_at_another_path_is_rejected(self) -> None:
        """A failure located in a copy of the body is not evidence about it."""
        elsewhere = Path('/tmp/another-checkout/elementwise_add.rs')
        log = (
            'error: invariant not satisfied at end of loop body\n'
            f'  --> {elsewhere}:{self.invariant}:13\n'
            'verification results:: 14 verified, 1 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'must name a line of the body'):
            self.driver._qualify_body(log, 1, self.driver.WRAP_BODY)

    def test_an_assertion_outside_the_body_is_rejected(self) -> None:
        """An admitted assertion is only evidence when the body raised it."""
        log = (
            'error: invariant not satisfied at end of loop body\n'
            f'  --> {self.driver.WRAP_BODY}:{self.invariant}:13\n'
            'error: assertion failed\n'
            '  --> wrap.rs:9:5\n'
            'verification results:: 14 verified, 2 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'must all be located in the body'):
            self.driver._qualify_body(log, 1, self.driver.WRAP_BODY)

    def test_the_committed_wrap_log_is_the_verdict_it_records(self) -> None:
        """The recorded body mutant must still be the run its log describes.

        The log is the transcript of a real run, so it is the strongest
        available check that the rule admits the observation it was written
        for rather than only the shapes its unit tests construct. It is
        committed with the repository root rewritten to ``<repo>``, so it also
        exercises the marker restoration a fresh log does not need.
        """
        driver = load_driver()
        log = (ROOT / 'tools/verifier-fixtures/verus-kernel/wrap.log').read_text(
            encoding='utf-8'
        )

        verdict = driver._qualify_body(log, 1, driver.WRAP_BODY)

        self.assertEqual(verdict['clause'], 'loop-invariant')

    def test_an_unlocated_invariant_is_rejected(self) -> None:
        """An invariant error with no location is not evidence about the body."""
        log = (
            'error: invariant not satisfied at loop head\n'
            'verification results:: 14 verified, 1 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'must name a line of the body'):
            self.driver._qualify_body(log, 1, self.driver.WRAP_BODY)

    def test_a_located_postcondition_beside_the_invariant_is_rejected(self) -> None:
        """A postcondition failure must disqualify the body tier even beside ours.

        The mutant tier exists to fail postconditions and admits them; the body
        tier's root states no clauses of its own, so it has no postcondition to
        fail. A rule that reused the mutant tier's permitted set would admit
        this log because the invariant is also present and both name the body.
        """
        log = (
            'error: invariant not satisfied at end of loop body\n'
            f'  --> {self.driver.WRAP_BODY}:{self.invariant}:13\n'
            'error: postcondition not satisfied\n'
            f'  --> {self.driver.WRAP_BODY}:{self._assertion_line()}:29\n'
            'verification results:: 14 verified, 2 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'disqualifying error'):
            self.driver._qualify_body(log, 1, self.driver.WRAP_BODY)


if __name__ == '__main__':
    unittest.main()
