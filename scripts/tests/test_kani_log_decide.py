"""Prove the Kani decision function implements VO-11b over every fact combination.

The decision is what the evidence gate ultimately trusts, so sampling a few
logs is not evidence enough. The suite enumerates the full cartesian product of
decision-relevant per-harness classes for one, two, and three harnesses — every
claim outcome, every witness state, every control disposition, and an
undeclared harness — and holds the product to three properties: the outcomes
never improve under degradation, a counterexample dominates everything below
it, and ``verified`` holds exactly when every claim stands. A data table pins
the cases whose *reason* matters, so a precedence change is a table edit rather
than a test rewrite.

The properties themselves live in :mod:`kani_decision_properties`, which states
them over the well-formed combinations — those the manifest declares in full.
A role-less harness is a structural error by VO-11b, so a combination carrying
one decides ``tool-error`` whatever else is true of it; testing the outcome
properties against those combinations would only re-test the refusal.

VO-11b also requires non-vacuity. Three deliberately broken decision functions —
one that always says ``verified``, one that reads only the success line, one
that ignores the manifest — are run over the corpus and must each be wrong
somewhere, which shows the properties can tell a wrong implementation from a
right one.

Examples
--------
>>> facts.decision_for((facts.HarnessFact('h::c', CLAIM, facts.SUCCESS),)).outcome
'verified'
>>> len(list(facts.occurrences(1)))
24
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kani_corpus_fixtures as corpus
import kani_decision_fixtures as facts
import kani_decision_properties as props
from docs_validation.kani_log import (
    BOUNDS, CLAIM, CONTROL, COUNTEREXAMPLE, FOCUSED, FULL_PROFILE, SKIPPED, TOOL_ERROR,
    VERIFIED, Decision, Harness, KaniLogError, Manifest, decide, from_error,
)
from kani_decision_properties import (
    claims_stand, controls_well_formed, declared_combinations, declared_witnesses, degrade,
    every_combination, names_of, summarise,
)


class DecisionTable(unittest.TestCase):
    """Hold each tabulated case to the outcome and reason it was written for."""

    def test_every_row_decides_as_it_declares(self):
        """Compare every row's outcome with the decision."""
        for row in facts.table()['rows']:
            with self.subTest(row=row['id']):
                self.assertEqual(facts.decide_row(row).outcome, row['outcome'],
                                 f"{row['id']} must decide {row['outcome']}: {row['why']}")

    def test_every_row_explains_itself(self):
        """Require each row to carry the reason it exists, which is what makes it reviewable."""
        for row in facts.table()['rows']:
            with self.subTest(row=row['id']):
                self.assertTrue(row.get('why'), f"{row['id']} must state why its outcome is right")

    def test_the_table_covers_every_outcome(self):
        """Require the table to reach every outcome the decision can return."""
        covered = {row['outcome'] for row in facts.table()['rows']}
        self.assertEqual(covered, set(facts.table()['outcomes']),
                         'the table must name an example of every outcome')

    def test_bounds_are_always_partial(self):
        """DL-10: no 1.2.1 decision may claim type-complete bounds."""
        for row in facts.table()['rows']:
            with self.subTest(row=row['id']):
                self.assertEqual(facts.decide_row(row).bounds, BOUNDS,
                                 'a 1.2.1 Kani decision must always report partial bounds')


class ExhaustivePrecedence(unittest.TestCase):
    """Hold the whole fact product to VO-11b's precedence and its consequences."""

    def test_counterexamples_dominate(self):
        """Require a failed claim assertion to decide ``counterexample`` whatever else happened."""
        checked, wrong = 0, []
        for combination in declared_combinations():
            if not any(fact.role == CLAIM and fact.status == facts.FAILURE
                       and not (fact.should_panic and fact.note) for fact in combination):
                continue
            checked += 1
            if facts.decision_for(combination).outcome != COUNTEREXAMPLE:
                wrong.append(names_of(combination))
        self.assertEqual(wrong, [], 'a failed claim assertion must decide counterexample')
        self.assertGreater(checked, 100, 'the product must reach counterexample many times')

    def test_degrading_never_improves_the_outcome(self):
        """Require the outcome never to become ``verified`` by way of a worse harness.

        ``verified`` is the only outcome that admits the evidence, so "never
        improves" is exact: a combination that was not verified must not become
        verified after one of its harnesses does worse.
        """
        improved = []
        for combination in declared_combinations():
            if facts.decision_for(combination).outcome == VERIFIED:
                continue
            for index in range(len(combination)):
                if facts.decision_for(degrade(combination, index)).outcome == VERIFIED:
                    improved.append(names_of(combination))
        self.assertEqual(improved, [], 'degrading a harness must never turn the run verified')

    def test_verified_exactly_when_every_claim_stands(self):
        """Require ``verified`` iff every claim stands.

        A witness is reported rather than folded into the outcome: MS-1 blocks
        an unsatisfied witness on its own reason code, so folding it here would
        report the same defect twice and would deny the corpus's
        deliberately-impossible cover the verdict Kani actually printed.
        """
        disagreeing = [names_of(combination) for combination in declared_combinations()
                       if (facts.decision_for(combination).outcome == VERIFIED)
                       != claims_stand(combination)]
        self.assertEqual(disagreeing, [], 'verified must hold exactly when every claim stands')

    def test_an_unsatisfied_witness_is_always_reported(self):
        """Require every declared cover to appear in the witness list with its own status."""
        disagreeing = [names_of(combination) for combination in declared_combinations()
                       if facts.decision_for(combination).witness_statuses
                       != declared_witnesses(combination)]
        self.assertEqual(disagreeing, [], 'every declared cover must be reported, whatever the outcome')

    def test_every_outcome_is_reachable(self):
        """Require the product to reach every outcome, so no property is stated over an empty set."""
        reached = {facts.decision_for(combination).outcome for combination in every_combination()}
        self.assertEqual(reached, set(facts.table()['outcomes']),
                         'the enumerated product must reach every outcome')

    def test_an_undeclared_harness_is_always_a_tool_error(self):
        """Require any combination naming a role-less harness to be refused."""
        checked, wrong = 0, []
        for combination in every_combination():
            if props.well_formed(combination):
                continue
            checked += 1
            decision = facts.decision_for(combination)
            if decision.outcome != TOOL_ERROR or 'does not declare' not in decision.reason:
                wrong.append(names_of(combination))
        self.assertEqual(wrong, [], 'a harness with no role must be a structural error naming it')
        self.assertGreater(checked, 100, 'the product must reach an undeclared harness many times')


class DecisionFacts(unittest.TestCase):
    """Hold the witness, control, and run-mode fields to what their readers require."""

    def test_witness_statuses_follow_the_declared_covers(self):
        """Require one witness per declared cover, in the manifest's order."""
        disagreeing = [names_of(combination) for combination in declared_combinations()
                       if len(facts.decision_for(combination).witness_statuses)
                       != len(facts.manifest_of(combination).declared_covers())
                       or not set(facts.decision_for(combination).witness_statuses)
                       <= set(props.WITNESSES)]
        self.assertEqual(disagreeing, [], 'there must be exactly one schema-admitted status per cover')

    def test_a_cover_is_matched_to_the_claim_that_declares_it(self):
        """Require two claims sharing witness wording to keep their own results.

        Two harnesses may describe their witnesses identically — the corpus
        runs one harness twice — so a lookup by wording alone would let a
        satisfied cover mask an unreachable one.
        """
        combination = (
            facts.HarnessFact('h::a', CLAIM, facts.SUCCESS, facts.SATISFIED,
                              cover_description='the witness'),
            facts.HarnessFact('h::b', CLAIM, facts.ABSENT, facts.SATISFIED,
                              cover_description='the witness'),
        )
        decision = facts.decision_for(combination)
        self.assertEqual(decision.witness_statuses, ('satisfied', 'unsatisfied'),
                         'the absent claim must not inherit the present claim\'s witness')
        self.assertEqual(decision.outcome, SKIPPED, 'the absent claim must still be skipped')

    def test_each_control_reports_its_disposition(self):
        """Require one disposition per control, drawn from the schema's enumeration."""
        disagreeing = [names_of(combination) for combination in declared_combinations()
                       if not controls_well_formed(combination)]
        self.assertEqual(disagreeing, [], 'every control must report one schema-admitted disposition')

    def test_a_control_never_becomes_a_claim(self):
        """Require a control's own failure to leave the claims' verdict alone.

        The corpus's ``seeded_wrapping_mutant`` run is exactly this shape: the
        only harness is a control that failed as designed, and the run decides
        ``verified`` with no claims at all. Reporting that as a counterexample
        would make every mutation run look like a disproof.
        """
        combination = (facts.HarnessFact('h::k', CONTROL, facts.AS_INTENDED),)
        decision = facts.decision_for(combination)
        self.assertEqual((decision.outcome, decision.negative_controls),
                         ('verified', ((True, 'rejected-as-intended'),)),
                         'a control rejected as intended must leave the run verified')

    def test_a_single_harness_run_is_never_full_profile(self):
        """Require a selected single harness to run in focused mode."""
        for name in ('selected_harness', 'verified'):
            with self.subTest(log=name):
                self.assertEqual(corpus.decision_for(name).run_mode, FOCUSED,
                                 'a run selecting one harness is not the full profile')

    def test_the_corpus_contains_a_full_profile_run(self):
        """Require at least one committed log to reach the mode VO-12's fixture needs.

        VO-12 admits a verifier record at ``bounded`` only from a full-profile
        run that also verified. ``insufficient_unwind`` reaches the mode for its
        own record but is resource-exhausted, so it cannot carry a positive
        record; before ``default_unwind`` the corpus proved the mode's absence
        rather than its presence. That log is captured with ``--default-unwind``
        so CBMC echoes ``--unwind`` for blocks the recording never asked to bound.
        """
        decisions = {name: corpus.decision_for(name) for name in corpus.log_names()}
        full_profile = {name for name, decision in decisions.items()
                        if decision.run_mode == FULL_PROFILE}
        self.assertEqual(full_profile, {'default_unwind', 'insufficient_unwind'},
                         'only a record whose whole declared set ran can be full-profile')
        reaching_bounded = {name for name in full_profile
                            if decisions[name].outcome == VERIFIED}
        self.assertEqual(reaching_bounded, {'default_unwind'},
                         'VO-12 needs a verified full-profile run, not merely a bounded one')

    def test_full_profile_requires_every_manifest_harness(self):
        """Require the whole manifest, with unwinding checks enabled, to be full-profile.

        Constructed rather than read from the corpus: every manifest harness
        reported, each with an echoed solver command carrying a bound.
        """
        combination = tuple(
            facts.HarnessFact(fact.name, fact.role, fact.status, fact.cover, fact.expected,
                              fact.should_panic, fact.note, bounded=True)
            for fact in (facts.HarnessFact('h::a', CLAIM, facts.SUCCESS),
                         facts.HarnessFact('h::k', CONTROL, facts.AS_INTENDED)))
        self.assertEqual(facts.decision_for(combination).run_mode, FULL_PROFILE,
                         'the whole manifest with unwinding checks enabled is the full profile')

    def test_full_profile_requires_enabled_unwinding_checks(self):
        """Require an unbounded run to stay focused even when the manifest is covered."""
        combination = tuple(
            facts.HarnessFact(fact.name, fact.role, fact.status, fact.cover)
            for fact in (facts.HarnessFact('h::a', CLAIM, facts.SUCCESS),
                         facts.HarnessFact('h::k', CONTROL, facts.AS_INTENDED)))
        self.assertEqual(facts.decision_for(combination).run_mode, FOCUSED,
                         'a run without an unwinding bound cannot be the full profile')

    def test_a_narrowed_manifest_is_what_makes_a_run_full_profile(self):
        """Require the same log to be full-profile for its record and focused for the crate.

        ``insufficient_unwind`` is decided against a one-harness selection of a
        nine-harness manifest; the same log against the whole crate decided
        focused, which is the comparison the mode turns on.
        """
        self.assertEqual(corpus.decision_for('insufficient_unwind').run_mode, FULL_PROFILE,
                         'the record\'s own selection is the full profile for that record')
        whole = decide(corpus.parse_log('insufficient_unwind'), corpus.crate_manifest())
        self.assertEqual(whole.run_mode, FOCUSED,
                         'the whole crate manifest is not covered by a one-harness log')

    def test_a_structural_refusal_decides_tool_error(self):
        """Require the corpus's killed run to decide ``tool-error`` with its reason."""
        decision = corpus.decision_for('truncated')
        self.assertEqual((decision.outcome, decision.bounds), ('tool-error', BOUNDS),
                         'a refused log must decide a tool error with partial bounds')
        self.assertIn('truncated', decision.reason, 'the decision must carry the structural reason')


class CorpusDecisions(unittest.TestCase):
    """Hold every committed log's decision to what it is recorded to decide."""

    def test_every_committed_log_decides_as_recorded(self):
        """Compare each decision's outcome, witnesses, controls, and run mode."""
        for name in corpus.log_names():
            with self.subTest(log=name):
                self.assertEqual(summarise(corpus.decision_for(name)), corpus.recorded(name),
                                 f'{name} must decide exactly what it is recorded to decide')

    def test_the_corpus_reaches_the_classes_vo_13_requires(self):
        """Require the corpus to contain each class VO-13 makes registration depend on."""
        decisions = [corpus.decision_for(name) for name in corpus.log_names()]
        outcomes = {decision.outcome for decision in decisions}
        self.assertTrue({'verified', 'counterexample', 'resource-exhausted', 'skipped',
                         'tool-error'} <= outcomes, 'the corpus must reach every structural outcome')
        self.assertTrue({'unsupported', 'solver-unknown'} & outcomes,
                        'the corpus must reach an unsupported or undetermined outcome')
        self.assertTrue(any('unsatisfied' in decision.witness_statuses for decision in decisions),
                        'the corpus must contain a log with an unsatisfied witness')

    def test_a_successful_run_may_still_have_an_unsatisfied_witness(self):
        """Require the corpus's vacuous run to be the log VO-11b names.

        Kani prints ``VERIFICATION:- SUCCESSFUL`` for a harness whose cover it
        could not reach, so the success line alone is not evidence. This is the
        case the non-vacuity check exists for.
        """
        decision = corpus.decision_for('vacuous_assumption')
        self.assertEqual(decision.outcome, 'solver-unknown',
                         'an unreachable witness must not decide verified')
        self.assertEqual(decision.witness_statuses, ('unsatisfied',),
                         'the unreachable witness must be reported unsatisfied')


def broken_always_verified(log, manifest):
    """Return a decision that ignores the log entirely."""
    return Decision(VERIFIED, BOUNDS, (), (), FOCUSED)


def broken_success_line_only(log, manifest):
    """Return a decision that trusts Kani's printed verdict and nothing else."""
    verdict = VERIFIED if all(block.succeeded for block in log.blocks) else COUNTEREXAMPLE
    return Decision(verdict, BOUNDS, (), (), FOCUSED)


def broken_manifest_ignored(log, manifest):
    """Return a decision taken against a manifest invented from the log itself.

    This is what "ignoring the manifest" means concretely: every harness the log
    reports is treated as a claim with no witness and no control role.
    """
    invented = Manifest(tuple(Harness(name, CLAIM) for name in log.harnesses))
    return decide(log, invented) if log.harnesses else broken_always_verified(log, manifest)


def _apply(decide_function, name: str):
    """Run one broken decision over one corpus log, refusing nothing it cannot parse."""
    try:
        log = corpus.parse_log(name)
    except KaniLogError as error:
        return from_error(error)
    return decide_function(log, corpus.manifest_for(name))


class BrokenDecisions(unittest.TestCase):
    """Run the corpus against three deliberately broken decisions and require each to fail.

    Each is a plausible shortcut rather than a strawman: trust the printed
    verdict, trust the success line, ignore the manifest. The tests do not
    assert *which* logs they get wrong, only that the corpus distinguishes each
    from the real decision, so the check survives the corpus growing without
    becoming a second copy of the expectations file.
    """

    def test_the_real_decision_gets_nothing_wrong(self):
        """Establish the reference the broken decisions are measured against."""
        wrong = [name for name in corpus.log_names()
                 if summarise(corpus.decision_for(name)) != corpus.recorded(name)]
        self.assertEqual(wrong, [], 'the real decision must match every recorded decision')

    def test_always_verified_is_wrong(self):
        """Reject a decision that ignores the log and reports success."""
        wrong = [name for name in corpus.log_names()
                 if summarise(_apply(broken_always_verified, name)) != corpus.recorded(name)]
        self.assertTrue(wrong, 'a decision that always says verified must be wrong somewhere')

    def test_the_success_line_alone_is_wrong(self):
        """Reject a decision that trusts the printed verdict and ignores covers and controls.

        The corpus's ``vacuous_assumption`` run prints a successful verdict
        while its only witness is unreachable, which is the case the shortcut
        cannot see.
        """
        wrong = [name for name in corpus.log_names()
                 if summarise(_apply(broken_success_line_only, name)) != corpus.recorded(name)]
        self.assertIn('vacuous_assumption', wrong,
                      'the success line alone must be wrong about the vacuous run')

    def test_ignoring_the_manifest_is_wrong(self):
        """Reject a decision that never reads roles, witnesses, or expected failures."""
        wrong = [name for name in corpus.log_names()
                 if summarise(_apply(broken_manifest_ignored, name)) != corpus.recorded(name)]
        self.assertIn('seeded_wrapping_mutant', wrong,
                      'ignoring the manifest must be wrong about the control-only run')


if __name__ == '__main__':
    unittest.main()
