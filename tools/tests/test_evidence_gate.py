"""Prove the evidence gate against its rule table over every abstract state (VO-1)."""
from __future__ import annotations

import collections
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation import evidence_gate as gate
from docs_validation.evidence_gate import AbstractRecord, Admission, Level, admit, all_states, is_valid

ROOT = Path(__file__).resolve().parents[2]
RULES = json.loads((ROOT / 'tools/tests/fixtures/evidence_gate_rules.json').read_text(encoding='utf-8'))
VALID_STATES = 86_400
RANK = {'proof': 4, 'bounded': 3, 'tested': 2, 'restricted': 1, 'rejected': 0}
# Worse values per field, for P1 (degradation monotonicity). Kind is excluded: it names the evidence type.
WORSE = {
    'outcome': {'verified': 0}, 'bounds': {'type-complete': 0, 'partial': 1},
    'witness': {'all-satisfied': 0, 'some-unsatisfied': 1, 'absent': 1},
    'controls': {'all-required-rejected-as-intended': 0},
    'trust': {'audited-none': 0, 'audited-all-covered': 1, 'audited-uncovered': 2, 'unaudited': 2},
    'exception': {'none': 0, 'active': 1}, 'binding': {'current': 0}, 'run_mode': {'full-profile': 0},
    'verdict_source': {'log-parser': 0},
}
DEFAULT_RANK = {'outcome': 1, 'controls': 1, 'exception': 2, 'binding': 1, 'run_mode': 1, 'verdict_source': 1}
REMEDY = {'outcome': 'verified', 'witness': 'all-satisfied', 'controls': 'all-required-rejected-as-intended',
          'trust': 'audited-none', 'binding': 'current', 'run_mode': 'full-profile', 'exception': 'none',
          'verdict_source': 'log-parser'}


def rank(field: str, value: str, kind: str) -> int:
    """Return how bad a field value is; larger is worse.

    A trust declaration exists only to carry an active exception, so for that
    kind an active exception is better than none.
    """
    if field == 'exception' and kind == 'trust-declaration':
        return {'active': 0, 'none': 1}.get(value, 2)
    return WORSE[field].get(value, DEFAULT_RANK.get(field, 0))


def interpret(state: AbstractRecord) -> tuple[str, tuple[str, ...]]:
    """An independent interpreter of the rule-table fixture, sharing no code with the gate."""
    values = vars(state)
    for rule in RULES['validity']:
        branch = rule['then'] if values[rule['if']['field']] in rule['if']['in'] else rule['else']
        value = values[branch['field']]
        if ('in' in branch and value not in branch['in']) or ('not_in' in branch and value in branch['not_in']):
            return RULES['invalid']['level'], tuple(RULES['invalid']['reasons'])
    reasons = tuple(rule['bad'][values[rule['field']]] for rule in RULES['blocking']
                    if (rule['kinds'] == 'any' or values['kind'] in rule['kinds']) and values[rule['field']] in rule['bad'])
    if reasons:
        return RULES['blocked']['level'], reasons
    if values['exception'] == 'active':
        return RULES['exception_active']['level'], tuple(RULES['exception_active']['reasons'])
    level = next(entry['level'] for entry in RULES['base_levels']
                 if all(values[key] == wanted for key, wanted in entry['when'].items()))
    return level, ()


def as_pair(admission: Admission) -> tuple[str, tuple[str, ...]]:
    """Return an admission as plain values for comparison with the interpreter."""
    return admission.level.value, admission.reasons


STATES = list(all_states())
ADMISSIONS = {state: admit(state) for state in STATES}
VALID = [state for state in STATES if is_valid(state)]


class RuleTable(unittest.TestCase):
    """MS-0 to MS-2: the implementation equals the fixture on all 345,600 states."""

    def test_domain_and_valid_state_counts(self):
        self.assertEqual(len(STATES), 345_600, 'the product domain has 345,600 states')
        self.assertEqual(len(VALID), VALID_STATES, 'the validity predicate admits 86,400 states')

    def test_fixture_domains_match_the_gate(self):
        self.assertEqual(tuple(RULES['domains']), gate.field_names(), 'the fixture names every field in order')
        for name, domain in zip(gate.field_names(), gate.DOMAINS):
            self.assertEqual(tuple(RULES['domains'][name]), domain, f'{name} values must agree')

    def test_gate_agrees_with_the_rule_table_everywhere(self):
        disagreements = [state for state in STATES if as_pair(ADMISSIONS[state]) != interpret(state)]
        self.assertEqual(disagreements[:3], [], f'{len(disagreements)} states disagree with the rule table')

    def test_every_level_and_reason_occurs_and_each_reason_can_stand_alone(self):
        levels = collections.Counter(ADMISSIONS[state].level for state in VALID)
        self.assertEqual(set(levels), set(Level), f'every level must occur: {levels}')
        sole = {admission.reasons[0] for admission in ADMISSIONS.values() if len(admission.reasons) == 1}
        every = {reason for admission in ADMISSIONS.values() for reason in admission.reasons}
        self.assertEqual(sole, every, f'reasons never alone: {sorted(every - sole)}')


class AdmissionProperties(unittest.TestCase):
    """P1 to P4 over the full enumeration."""

    def test_p1_degradation_never_raises_the_level(self):
        valid = set(VALID)
        for state in VALID:
            level = RANK[ADMISSIONS[state].level.value]
            for field, ranks in WORSE.items():
                current = getattr(state, field)
                for value in RULES['domains'][field]:
                    worse = replace(state, **{field: value})
                    if worse in valid and rank(field, value, state.kind) > rank(field, current, state.kind):
                        self.assertLessEqual(RANK[ADMISSIONS[worse].level.value], level, f'{state} -> {field}={value}')

    def test_p2_rejection_exactly_when_blocked_and_each_remedy_removes_one_reason(self):
        field_of = {reason: rule['field'] for rule in RULES['blocking'] for reason in rule['bad'].values()}
        for state in VALID:
            admission = ADMISSIONS[state]
            self.assertEqual(admission.level is Level.REJECTED, bool(admission.reasons)
                             and admission.reasons != ('exception-active',), f'{state}')
            for reason in admission.reasons:
                if reason in {'not-run', 'trust-without-exception', 'exception-active'}:
                    continue
                remedied = replace(state, **{field_of[reason]: REMEDY[field_of[reason]]})
                if is_valid(remedied):
                    expected = tuple(item for item in admission.reasons if item != reason)
                    actual = tuple(item for item in ADMISSIONS[remedied].reasons if item != 'exception-active')
                    self.assertEqual(actual, expected, f'{state} remedy {reason}')

    def test_p3_exceptions_never_satisfy_a_component(self):
        satisfying = {Level.PROOF, Level.BOUNDED, Level.TESTED}
        for state in VALID:
            if state.exception != 'none':
                self.assertNotIn(ADMISSIONS[state].level, satisfying, f'{state}')

    def test_p4_partial_bounds_never_reach_proof(self):
        for state in VALID:
            if state.bounds == 'partial':
                self.assertNotEqual(ADMISSIONS[state].level, Level.PROOF, f'{state}')


BEST = AbstractRecord('deductive', 'verified', 'not-applicable', 'all-satisfied', 'all-required-rejected-as-intended',
                      'audited-none', 'none', 'current', 'full-profile', 'log-parser')


def scenario(**changes: str) -> AbstractRecord:
    """Build a scenario from a fully admissible deductive record by changing named fields."""
    return replace(BEST, **changes)


# Upstream scenarios, derived from the bet register, the proof ledger, and technical design §17, not from ADR-0009.
SCENARIOS = [
    ('B01 suppress a failed harness', scenario(kind='bounded', bounds='type-complete', outcome='skipped'), 'rejected', 'outcome-skipped'),
    ('B01 trust a self-reported verdict', scenario(verdict_source='self-reported'), 'rejected', 'verdict-self-reported'),
    ('B02 always-Err executor', scenario(witness='some-unsatisfied'), 'rejected', 'witness-some-unsatisfied'),
    ('B02 assumed executor postcondition', scenario(trust='audited-uncovered'), 'rejected', 'trust-uncovered'),
    ('B08 metadata from a different executable', scenario(binding='stale'), 'rejected', 'binding-stale'),
    ('B08 focus mode as release evidence', scenario(run_mode='focused'), 'rejected', 'run-focused'),
    ('B08 bounded Kani labelled unbounded', scenario(kind='bounded', bounds='partial'), 'bounded', None),
    ('PF14 swap a compiled body', scenario(binding='stale'), 'rejected', 'binding-stale'),
    ('§17.1 timeout', scenario(outcome='resource-exhausted'), 'rejected', 'outcome-resource-exhausted'),
    ('§17.1 unsupported feature', scenario(outcome='unsupported'), 'rejected', 'outcome-unsupported'),
    ('§17.1 failed unwinding assertion', scenario(kind='bounded', bounds='type-complete', outcome='counterexample'),
     'rejected', 'outcome-counterexample'),
    ('§17.7 empty generator', scenario(kind='test', witness='absent'), 'rejected', 'witness-absent'),
    ('§17.7 control fails on an unrelated parse error', scenario(controls='some-rejected-otherwise'), 'rejected',
     'control-some-rejected-otherwise'),
    ('Exception never substitutes for proof', scenario(exception='active'), 'restricted', 'exception-active'),
    ('Planned record', scenario(kind='none', outcome='not-run', witness='absent', controls='required-missing',
                                binding='incomplete'), 'rejected', 'not-run'),
]


class Scenarios(unittest.TestCase):
    """The upstream scenario corpus is decided the same way by the gate and the rule table."""

    def test_scenarios(self):
        for name, state, level, reason in SCENARIOS:
            with self.subTest(scenario=name):
                admission = admit(state)
                self.assertEqual(admission.level.value, level, f'{name} must be {level}')
                if reason is not None:
                    self.assertIn(reason, admission.reasons, f'{name} must report {reason}')
                self.assertEqual(as_pair(admission), interpret(state), f'{name} must match the rule table')

    def test_bounded_kani_never_satisfies_a_proof_only_component(self):
        state = scenario(kind='bounded', bounds='partial')
        self.assertNotIn(admit(state).level.value, {'proof'}, 'partial bounds cannot satisfy a proof-only component')


def mutated(edit) -> dict:
    """Return a copy of the rule table with one seeded fault."""
    rules = json.loads(json.dumps(RULES))
    edit(rules)
    return rules


def interpret_with(rules: dict, state: AbstractRecord) -> tuple[str, tuple[str, ...]]:
    """Interpret a state under a mutated rule table."""
    global RULES
    original, RULES = RULES, rules
    try:
        return interpret(state)
    finally:
        RULES = original


SEEDED_FAULTS = {
    'resource-exhausted treated as verified': lambda r: r['blocking'][0]['bad'].pop('resource-exhausted'),
    'trust ignored': lambda r: r['blocking'].pop(3),
    'active exception keeps the base level': lambda r: r.__setitem__('exception_active', {'level': 'proof', 'reasons': []}),
    'partial bounds mapped to proof': lambda r: r['base_levels'][2].__setitem__('level', 'proof'),
    'some-rejected-otherwise accepted': lambda r: r['blocking'][2]['bad'].pop('some-rejected-otherwise'),
}


class SeededFaults(unittest.TestCase):
    """Each seeded rule-table fault would be caught by the exhaustive agreement test."""

    def test_each_fault_disagrees_with_the_gate_somewhere(self):
        for name, edit in SEEDED_FAULTS.items():
            with self.subTest(fault=name):
                rules = mutated(edit)
                caught = next((state for state in VALID if interpret_with(rules, state) != as_pair(ADMISSIONS[state])),
                              None)
                self.assertIsNotNone(caught, f'seeded fault {name!r} must change some admission')


if __name__ == '__main__':
    unittest.main()
