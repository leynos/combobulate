"""Prove pre-registration freezes every control field and amendment history (VO-11)."""
from __future__ import annotations

import copy
import socket
import sys
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hypothesis import given, settings, strategies as st
from jsonschema import Draft202012Validator, ValidationError

from docs_validation.context import ValidationContext
from docs_validation.preregistration import (
    FROZEN_FIELDS, OUTCOME_VERDICTS, check_acceptance_controls, check_amendment_chain,
    check_completeness, check_measurement_binding, check_registration_declarations, check_sources,
    frozen_digest,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTER = ValidationContext(ROOT).load('spec/acceptance-controls.json')
CONTROL = REGISTER['controls'][0]
CI_CONTROL = next(item for item in REGISTER['controls'] if item['id'] == 'AC-07')
SPONSOR = 'leynos'
REGISTER_VALIDATOR = Draft202012Validator(
    ValidationContext(ROOT).load('spec/acceptance-controls.schema.json'),
    format_checker=Draft202012Validator.FORMAT_CHECKER,
)
RECORD_VALIDATOR = Draft202012Validator(
    ValidationContext(ROOT).load('spec/measurement-record.schema.json'),
    format_checker=Draft202012Validator.FORMAT_CHECKER,
)
RECORD_OUTCOMES = sorted(OUTCOME_VERDICTS)
LATEST_CONTROL_AMENDMENT_DATE = CONTROL['amendments'][-1]['date']
TEST_MEASUREMENT_DATE = (date.fromisoformat(LATEST_CONTROL_AMENDMENT_DATE) + timedelta(days=1)).isoformat()


def amended(control: dict, field: str, value: object) -> dict:
    """Return a copy with one frozen field changed through an approved amendment."""
    edited = copy.deepcopy(control)
    edited['frozen'][field] = value
    new_digest = frozen_digest(edited)
    previous_date = edited['amendments'][-1]['date'] if edited['amendments'] else edited['frozen']['registered_on']
    amendment_date = (date.fromisoformat(previous_date) + timedelta(days=1)).isoformat()
    edited['amendments'].append({'date': amendment_date, 'approved_by': SPONSOR,
                                 'approval_reference': 'https://example.org/approval',
                                 'replaces': edited['digest'], 'new_digest': new_digest, 'reason': 'Test.'})
    edited['digest'] = new_digest
    return edited


def record(outcome: str, purpose: str = 'acceptance', digest: str | None = None) -> dict:
    """Build one schema-valid measurement record for the first control."""
    entry = {'id': 'fixture', 'purpose': purpose, 'control_ids': [CONTROL['id']],
             'control_digest': None if purpose == 'calibration' else (digest or CONTROL['digest']),
             'recorded_on': TEST_MEASUREMENT_DATE,
             'hardware': {'class': 'github-hosted-runner', 'cpu_model': 'fixture', 'cores': 4, 'threads': 4,
                          'vcpus': 4, 'memory_gib': 16, 'architecture': 'x64',
                          'os_family': 'Ubuntu 24.04', 'kernel_major': 6},
             'toolchains': {'rust': 'nightly-2026-08-27', 'codegen_backend': 'Cranelift',
                            'linker': 'mold 2.41.0', 'verus': '0.2026.09.06.8dea4a2 with Z3 4.16.0',
                            'kani': '0.67.0'},
             'workloads': [{'id': 'w', 'description': 'Fixture.', 'command': 'true',
                                              'metric': 'wall time', 'unit': 's', 'samples': [1], 'median': 1}]}
    if purpose == 'acceptance':
        entry['outcome'] = outcome
        entry['runner_image'] = 'ubuntu-24.04'
        entry['runner_metadata'] = {'image_os': 'ubuntu24', 'image_version': '20261012.1'}
    RECORD_VALIDATOR.validate(entry)
    return entry


def ci_record(outcome: str, conclusions: list[tuple[str, float]]) -> dict:
    """Build an AC-07 record in newest-first order with timestamped job attempts."""
    entry = record(outcome, digest=CI_CONTROL['digest'])
    entry['control_ids'] = [CI_CONTROL['id']]
    workload = entry['workloads'][0]
    workload['id'] = 'ci-build-test'
    attempts = []
    newest_start = datetime(2026, 10, 12, 12, tzinfo=UTC)
    for index, (conclusion, seconds) in enumerate(conclusions):
        start = newest_start - timedelta(minutes=index)
        finish = start + timedelta(seconds=seconds)
        attempts.append({'run_id': str(index + 1), 'run_number': index + 1, 'attempt': 1,
                         'conclusion': conclusion, 'wall_seconds': seconds,
                         'started_at': start.isoformat().replace('+00:00', 'Z'),
                         'completed_at': finish.isoformat().replace('+00:00', 'Z'),
                         'url': f'https://github.com/leynos/combobulate/actions/runs/{index + 1}'})
    workload['attempts'] = attempts
    workload['samples'] = [attempt['wall_seconds'] for attempt in attempts]
    RECORD_VALIDATOR.validate(entry)
    return entry


class Registration(unittest.TestCase):
    """VO-11: frozen protocols are typed, digested, and governed by an approved chain."""

    def test_committed_register_passes(self):
        """Validate every registered control and source in the committed register."""
        # Home-path checks catch user names; a generic CI account name is ordinary text.
        check_acceptance_controls(ValidationContext(ROOT), (socket.gethostname(),))

    def test_register_lists_the_frozen_fields(self):
        """Require the register to name the fields used by its digest."""
        self.assertEqual(REGISTER['frozen_fields'], list(FROZEN_FIELDS), 'the register must state its frozen fields')

    def test_register_frozen_fields_match_digest_implementation(self):
        """Keep the declared frozen fields aligned with the digest implementation."""
        check_registration_declarations(REGISTER)
        candidate = copy.deepcopy(REGISTER)
        candidate['frozen_fields'][-1] = 'unhashed-field'
        with self.assertRaisesRegex(AssertionError, 'must match the executable digest fields',
                                    msg='the declared frozen fields must match the digest implementation'):
            check_registration_declarations(candidate)

    def test_missing_calibration_reference_fails(self):
        """Reject a control that omits its required calibration reference."""
        control = copy.deepcopy(CONTROL)
        del control['frozen']['calibration']
        with self.assertRaisesRegex(AssertionError, 'lacks frozen fields: calibration'):
            check_completeness(control)

    def test_threshold_and_digest_edited_together_fail(self):
        """Reject a changed threshold even when its digest is recalculated."""
        control = copy.deepcopy(CONTROL)
        control['frozen']['decision_rule']['thresholds'] = {'anything': 1}
        control['digest'] = frozen_digest(control)
        with self.assertRaisesRegex(AssertionError, 'digest is not the end of its amendment chain'):
            check_amendment_chain(control, SPONSOR)

    def test_correct_amendment_passes(self):
        """Accept a correctly approved amendment with a matching digest chain."""
        check_amendment_chain(amended(CONTROL, 'seeds', [7]), SPONSOR)

    def test_amendment_before_first_measurement_remains_authorized(self):
        """Allow an amendment made before its first acceptance measurement."""
        control = amended(CONTROL, 'seeds', [7])
        measurement = record('pass', digest=control['digest'])
        measurement['recorded_on'] = (
            date.fromisoformat(control['amendments'][-1]['date']) + timedelta(days=1)
        ).isoformat()
        check_amendment_chain(control, SPONSOR, [measurement])
        self.assertTrue(check_measurement_binding(control, measurement),
                        'a measurement after an approved amendment binds the amended digest')

    def test_amendment_cannot_backdate_measurement_authority(self):
        """Reject an amendment dated before its preceding effective date."""
        control = amended(CONTROL, 'seeds', [7])
        control['amendments'][0]['date'] = '2026-10-10'
        between_registration_and_record = record('pass', digest=control['digest'])
        between_registration_and_record['recorded_on'] = '2026-10-11'
        with self.assertRaisesRegex(AssertionError, 'amendment date cannot predate its previous effective date'):
            check_amendment_chain(control, SPONSOR, [between_registration_and_record])

    def test_amendment_date_must_follow_the_previous_amendment(self):
        """Reject a chain whose amendment dates move backwards."""
        control = amended(amended(CONTROL, 'seeds', [7]), 'seeds', [8])
        control['amendments'][-1]['date'] = '2026-10-11'
        with self.assertRaisesRegex(AssertionError, 'amendment date cannot predate its previous effective date'):
            check_amendment_chain(control, SPONSOR)

    def test_register_outcome_map_matches_executable_verdicts(self):
        """Keep schema and runtime outcome mappings consistent."""
        check_registration_declarations(REGISTER)
        altered_maps = (
            dict(OUTCOME_VERDICTS) | {'new-outcome': 'fail'},
            {key: value for key, value in OUTCOME_VERDICTS.items() if key != 'missing'},
            dict(OUTCOME_VERDICTS) | {'resource-exhausted': 'pass'},
        )
        for outcome_map in altered_maps:
            with self.subTest(outcome_map=outcome_map):
                candidate = copy.deepcopy(REGISTER)
                candidate['outcome_verdicts'] = outcome_map
                with self.assertRaisesRegex(AssertionError, 'must match the executable outcome mapping',
                                            msg='runtime semantics must reject a changed outcome map'):
                    check_registration_declarations(candidate)
                with self.assertRaises(ValidationError, msg='the register schema must reject a changed outcome map'):
                    REGISTER_VALIDATOR.validate(candidate)

    def test_amendment_needs_the_sponsor(self):
        """Reject an amendment approved by someone other than the sponsor."""
        control = amended(CONTROL, 'seeds', [7])
        control['amendments'][-1]['approved_by'] = 'someone-else'
        with self.assertRaisesRegex(AssertionError, 'not approved by the sponsor'):
            check_amendment_chain(control, SPONSOR)

    def test_amendment_on_measurement_date_requires_a_new_control_identifier(self):
        """Reject an amendment made on an acceptance measurement date."""
        control = amended(CONTROL, 'seeds', [7])
        with self.assertRaisesRegex(AssertionError, 'must predate the earliest acceptance measurement'):
            check_amendment_chain(control, SPONSOR, [record('pass')])

    def test_protocol_content_is_typed_after_digest_recalculation(self):
        """Validate frozen protocol types even when the digest is recomputed."""
        for field, value in (('seeds', None), ('registered_on', 'not-a-date'), ('decision_rule', 'bad threshold')):
            with self.subTest(field=field):
                control = copy.deepcopy(CONTROL)
                if field == 'decision_rule':
                    control['frozen'][field]['thresholds']['budget'] = value
                else:
                    control['frozen'][field] = value
                digest = frozen_digest(control)
                control['registered_digest'] = digest
                control['digest'] = digest
                candidate = copy.deepcopy(REGISTER)
                candidate['controls'] = [control if item['id'] == control['id'] else item
                                          for item in REGISTER['controls']]
                with self.assertRaises(ValidationError,
                                       msg=f'{field} must fail schema validation with a recomputed digest'):
                    REGISTER_VALIDATOR.validate(candidate)

    def test_changed_source_needs_an_amendment(self):
        """Reject missing or changed bytes for a registered source."""
        control = copy.deepcopy(CI_CONTROL)
        sources = {source['path']: source['sha256'] for source in control['frozen']['workload']['sources']}
        check_sources(control, sources)
        sources['.github/workflows/ci.yml'] = '0' * 64
        with self.assertRaisesRegex(AssertionError, 'AC-07 source .github/workflows/ci.yml changed since registration',
                                    msg='changed source bytes must require a registered amendment'):
            check_sources(control, sources)
        with self.assertRaisesRegex(AssertionError, 'AC-07 source .github/workflows/ci.yml is missing',
                                    msg='every registered source must be supplied to the pure rule'):
            check_sources(control, {})

    def test_every_frozen_field_changes_the_digest(self):
        """Exercise every frozen field against the digest and chain checks."""
        exercised: set[str] = set()

        @settings(max_examples=200, derandomize=True, deadline=None)
        @given(st.sampled_from(FROZEN_FIELDS), st.integers())
        def mutate(field: str, value: int) -> None:
            """Replace one sampled frozen field and verify that it cannot bypass the digest check."""
            exercised.add(field)
            control = copy.deepcopy(CONTROL)
            control['frozen'][field] = {'mutated': value}
            self.assertNotEqual(frozen_digest(control), CONTROL['digest'], f'{field} must be covered by the digest')
            with self.assertRaises(AssertionError):
                check_amendment_chain(control, SPONSOR)

        mutate()
        self.assertEqual(exercised, set(FROZEN_FIELDS), 'every frozen field must be exercised')

    @settings(max_examples=40, derandomize=True, deadline=None)
    @given(st.lists(st.integers(min_value=-1_000_000, max_value=1_000_000)
                    .filter(lambda value: [value] != CONTROL['frozen']['seeds']),
                    min_size=2, max_size=6, unique=True))
    def test_generated_amendment_chains_reject_invalid_mutations(self, seed_values):
        """Exercise valid amendment chains and generated authority, ancestry, chronology, repetition, and cutoff failures."""
        chain = copy.deepcopy(CONTROL)
        for seed in seed_values:
            chain = amended(chain, 'seeds', [seed])

        check_amendment_chain(chain, SPONSOR)
        valid_measurement = record('pass', digest=chain['digest'])
        valid_measurement['recorded_on'] = (
            date.fromisoformat(chain['amendments'][-1]['date']) + timedelta(days=1)
        ).isoformat()
        check_amendment_chain(chain, SPONSOR, [valid_measurement])

        broken_ancestry = copy.deepcopy(chain)
        previous_digest = broken_ancestry['amendments'][-1]['replaces']
        broken_ancestry['amendments'][-1]['replaces'] = 'f' * 64 if previous_digest != 'f' * 64 else 'e' * 64
        with self.assertRaisesRegex(AssertionError, 'does not replace digest'):
            check_amendment_chain(broken_ancestry, SPONSOR)

        repeated_digest = copy.deepcopy(chain)
        repeated_digest['amendments'][-1]['new_digest'] = repeated_digest['registered_digest']
        with self.assertRaisesRegex(AssertionError, 'repeats a digest'):
            check_amendment_chain(repeated_digest, SPONSOR)

        non_monotonic_date = copy.deepcopy(chain)
        previous_date = date.fromisoformat(non_monotonic_date['amendments'][-2]['date'])
        non_monotonic_date['amendments'][-1]['date'] = (previous_date - timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(AssertionError, 'cannot predate its previous effective date'):
            check_amendment_chain(non_monotonic_date, SPONSOR)

        wrong_sponsor = copy.deepcopy(chain)
        wrong_sponsor['amendments'][-1]['approved_by'] = 'another-sponsor'
        with self.assertRaisesRegex(AssertionError, 'not approved by the sponsor'):
            check_amendment_chain(wrong_sponsor, SPONSOR)

        first_generated_amendment = chain['amendments'][len(CONTROL['amendments'])]
        cutoff_measurement = record('pass', digest=chain['digest'])
        cutoff_measurement['recorded_on'] = first_generated_amendment['date']
        with self.assertRaisesRegex(AssertionError, 'must predate the earliest acceptance measurement'):
            check_amendment_chain(chain, SPONSOR, [cutoff_measurement])


if __name__ == '__main__':
    unittest.main()
