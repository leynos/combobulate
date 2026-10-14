"""Verify committed evidence without overwriting stale, malformed, or falsified reports."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.freeze import RevisionJsonReader
from docs_validation.preregistration import check_acceptance_controls

import check_docs

ROOT = Path(__file__).resolve().parents[2]


class ValidationReport(unittest.TestCase):
    """Run the complete checker on copied source inputs and inspect persistent side effects."""

    def setUp(self) -> None:
        """Run report checks against disposable source copies, away from repository files."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        # `.github` holds registered acceptance-control sources; build outputs stay behind.
        for folder in ('.github', 'docs', 'scripts', 'spec', 'tools'):
            shutil.copytree(ROOT / folder, self.root / folder, ignore=shutil.ignore_patterns('__pycache__', 'target'))
        for path in ROOT.iterdir():
            # Linked worktrees store a .git pointer file that is invalid in this fixture.
            if path.is_file() and path.name != '.git':
                shutil.copy2(path, self.root / path.name)
        self.report = self.root / 'docs/validation-results.json'
        self.initialise_repository()
        self.assertEqual(self.run_main(['--write']), 0)

    def initialise_repository(self) -> None:
        """Give the current-revision checker a committed fixture checkout."""
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(['git', 'add', '-A'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(
            ['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.org',
             '-c', 'commit.gpgsign=false', 'commit', '-q', '-m', 'Create validation fixture'],
            cwd=self.root, check=True, capture_output=True,
        )

    def run_main(self, arguments: list[str]) -> int:
        """Execute the checker against copied inputs and capture its evidence output."""
        with patch.object(check_docs, 'ROOT', self.root), contextlib.redirect_stdout(io.StringIO()):
            return check_docs.main(arguments)

    def source_bytes(self) -> dict[str, bytes]:
        """Snapshot repository inputs and report, excluding incidental Python caches."""
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*')
                if path.is_file() and '__pycache__' not in path.parts}

    def assert_command_rejects(self, pattern: str, expectation: str) -> None:
        """Require a command-boundary rejection without replacing committed evidence."""
        report_before = self.report.read_bytes()
        with self.assertRaisesRegex(SystemExit, pattern, msg=expectation):
            self.run_main([])
        self.assertEqual(self.report.read_bytes(), report_before,
                         f'{expectation}; the validation report must remain untouched')

    @staticmethod
    def acceptance_record(record_id: str, control_id: str, control_digest: str,
                          recorded_on: str) -> dict[str, object]:
        """Create a schema-valid acceptance record for composition-path rejection cases."""
        return {
            'id': record_id,
            'purpose': 'acceptance',
            'control_ids': [control_id],
            'control_digest': control_digest,
            'recorded_on': recorded_on,
            'runner_image': 'ubuntu-24.04',
            'outcome': 'pass',
            'hardware': {
                'class': 'github-hosted-runner', 'cpu_model': 'fixture CPU',
                'cores': 4, 'threads': 4, 'vcpus': 4, 'memory_gib': 16,
                'architecture': 'x64',
                'os_family': 'Ubuntu 24.04', 'kernel_major': 6,
            },
            'runner_metadata': {'image_os': 'ubuntu24', 'image_version': '20261012.1'},
            'toolchains': {
                'rust': 'nightly-2026-08-27', 'codegen_backend': 'Cranelift',
                'linker': 'mold 2.41.0',
                'verus': '0.2026.09.06.8dea4a2 with Z3 4.16.0', 'kani': '0.67.0',
            },
            'workloads': [{
                'id': 'cardinality', 'description': 'Fixture workload',
                'command': 'fixture command', 'metric': 'wall time', 'unit': 's',
                'samples': [1.0], 'median': 1.0,
            }],
        }

    def test_successful_default_check_does_not_mutate_inputs_or_report(self) -> None:
        """Keep the default validation path read-only after confirming a valid report."""
        before = self.source_bytes()
        self.assertEqual(self.run_main([]), 0)
        self.assertEqual(self.source_bytes(), before)

    def test_invalid_json_report_is_rejected_without_replacement(self) -> None:
        """Reject malformed prior evidence without silently replacing the report."""
        self.report.write_text('{')
        before = self.source_bytes()
        with self.assertRaises(SystemExit):
            self.run_main([])
        self.assertEqual(self.source_bytes(), before)

    def test_stale_and_falsified_reports_fail_without_mutation(self) -> None:
        """Reject altered counts, status, or omitted checks without changing that evidence."""
        original = json.loads(self.report.read_text())
        mutations = ('count', 'status', 'not_run')
        for mutation in mutations:
            report = json.loads(json.dumps(original))
            if mutation == 'count':
                next(row for row in report['checks'] if row.get('count') == 1)['count'] = True
            elif mutation == 'status':
                report['status'] = 'fail'
            else:
                report['not_run'] = []
            self.report.write_text(json.dumps(report) + '\n')
            before = self.source_bytes()
            with self.subTest(mutation=mutation), self.assertRaisesRegex(SystemExit, 'Validation report drift'):
                self.run_main([])
            self.assertEqual(self.source_bytes(), before)

    def test_source_failure_leaves_report_untouched_even_with_write_requested(self) -> None:
        """Validate every source before allowing explicit report regeneration."""
        (self.root / 'spec/cost-cases.json').write_text('{')
        for arguments in ([], ['--write']):
            before = self.source_bytes()
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                self.run_main(arguments)
            self.assertEqual(self.source_bytes(), before)

    def test_invalid_workflow_yaml_is_reported_without_overwriting_evidence(self) -> None:
        """Translate malformed workflow YAML at the checker boundary and preserve the report."""
        (self.root / '.github/workflows/ci.yml').write_text('jobs: [\n', encoding='utf-8')
        report_before = self.report.read_bytes()
        with self.assertRaisesRegex(SystemExit, 'Invalid YAML in .github/workflows/ci.yml',
                                    msg='malformed workflow YAML must fail as a validation result'):
            self.run_main(['--write'])
        self.assertEqual(self.report.read_bytes(), report_before,
                         'invalid workflow YAML must not replace the committed validation report')

    def test_missing_registered_workload_source_is_reported_at_command_boundary(self) -> None:
        """Convert source-reader failures into a validation result without mutating the report."""
        (self.root / 'tools/calibration/cardinality-probe/verus/cardinality.rs').unlink()
        report_before = self.report.read_bytes()
        with self.assertRaisesRegex(SystemExit, 'Unable to read registered workload source',
                                    msg='missing source bytes must fail through the checker boundary'):
            self.run_main(['--write'])
        self.assertEqual(self.report.read_bytes(), report_before,
                         'a missing registered source must not replace the committed validation report')

    def test_modified_registered_source_digest_is_rejected_by_command(self) -> None:
        """Reject changed bytes at the real checker entrypoint against registered source digests."""
        source = self.root / 'tools/calibration/cardinality-probe/verus/cardinality.rs'
        source.write_bytes(source.read_bytes() + b'\n')
        self.assert_command_rejects(
            r'AC-01 source .* changed since registration',
            'the command path must reject bytes that no longer match AC-01 registration',
        )

    def test_missing_ac07_calibration_reference_is_rejected_by_command(self) -> None:
        """Require the command path to resolve AC-07's registered CI history record."""
        (self.root / 'spec/calibration/ci-history.json').unlink()
        self.assert_command_rejects(
            r'AC-07 cites missing calibration record spec/calibration/ci-history\.json',
            'AC-07 must not pass when its referenced calibration record is missing',
        )

    def test_ci_runner_image_mismatch_is_rejected_by_command(self) -> None:
        """Bind the workflow runner to AC-07 through the composition path."""
        workflow = self.root / '.github/workflows/ci.yml'
        contents = workflow.read_text(encoding='utf-8')
        self.assertIn('runs-on: ubuntu-24.04', contents,
                      'the fixture workflow must contain the registered runner image')
        workflow.write_text(contents.replace('runs-on: ubuntu-24.04', 'runs-on: ubuntu-latest', 1),
                             encoding='utf-8')
        self.assert_command_rejects(
            r"build-test runner 'ubuntu-latest' does not match AC-07 image ubuntu-24\.04",
            'the command path must reject a workflow runner that differs from AC-07',
        )

    def test_acceptance_measurement_with_unknown_control_digest_is_rejected_by_command(self) -> None:
        """Reject acceptance evidence that cites no digest in the registered control history."""
        register = json.loads((self.root / 'spec/acceptance-controls.json').read_text(encoding='utf-8'))
        control = next(item for item in register['controls'] if item['id'] == 'AC-01')
        last_effective_date = (control['amendments'][-1]['date'] if control['amendments']
                               else control['frozen']['registered_on'])
        recorded_on = (date.fromisoformat(last_effective_date) + timedelta(days=1)).isoformat()
        record = self.acceptance_record(
            'unknown-control-digest', 'AC-01', 'f' * 64, recorded_on,
        )
        measurements = self.root / 'spec/measurements'
        measurements.mkdir()
        (measurements / 'unknown-control-digest.json').write_text(
            json.dumps(record), encoding='utf-8',
        )
        self.assert_command_rejects(
            r'unknown-control-digest cites unknown digest .* for AC-01',
            'the command path must reject acceptance evidence with an unregistered digest',
        )

    def test_decoded_json_strings_cannot_hide_host_identities(self) -> None:
        """Reject escaped host identities in calibration and acceptance JSON."""
        calibration_path = self.root / 'spec/calibration/verifier-probe.json'
        original_calibration = json.loads(calibration_path.read_text(encoding='utf-8'))
        register = json.loads((self.root / 'spec/acceptance-controls.json').read_text(encoding='utf-8'))
        control = next(item for item in register['controls'] if item['id'] == 'AC-01')
        last_effective_date = (control['amendments'][-1]['date'] if control['amendments']
                               else control['frozen']['registered_on'])
        recorded_on = (date.fromisoformat(last_effective_date) + timedelta(days=1)).isoformat()
        measurements = self.root / 'spec/measurements'
        measurements.mkdir()
        measurement_path = measurements / 'escaped-identity.json'
        original_measurement = self.acceptance_record(
            'escaped-identity', 'AC-01', control['digest'], recorded_on,
        )
        source_records = (
            ('calibration', calibration_path, original_calibration),
            ('measurement', measurement_path, original_measurement),
        )
        encoded_values = (
            ('home path', '/home/alice/bin/verus', r'\u002fhome\u002falice\u002fbin\u002fverus', (),
             'contains a home path'),
            ('host name', 'measured on build-box-7', r'measured on build-\u0062ox-7', ('build-box-7',),
             "contains host identity 'build-box-7'"),
        )

        for record_type, source, original in source_records:
            for label, decoded, encoded, extra_names, expected_error in encoded_values:
                with self.subTest(record_type=record_type, identity=label):
                    record = json.loads(json.dumps(original))
                    record['workloads'][0]['command'] = decoded
                    serialized = json.dumps(record)
                    escaped = serialized.replace(decoded, encoded, 1)
                    self.assertNotIn(
                        decoded,
                        escaped,
                        f'{label} regression fixture must hide the identity from the raw-text scan',
                    )
                    source.write_text(escaped, encoding='utf-8')
                    with self.assertRaisesRegex(
                        AssertionError,
                        expected_error,
                        msg=f'the composition path must reject a decoded {label} in {record_type} JSON',
                    ):
                        check_acceptance_controls(ValidationContext(self.root), extra_names)

    def test_acceptance_purpose_record_in_calibration_directory_is_rejected_by_command(self) -> None:
        """Keep acceptance-purpose records out of the calibration-only directory."""
        register = json.loads((self.root / 'spec/acceptance-controls.json').read_text(encoding='utf-8'))
        control = next(item for item in register['controls'] if item['id'] == 'AC-01')
        record = self.acceptance_record(
            'misplaced-acceptance-record', 'AC-01', control['digest'], control['frozen']['registered_on'],
        )
        (self.root / 'spec/calibration/misplaced-acceptance-record.json').write_text(
            json.dumps(record), encoding='utf-8',
        )
        self.assert_command_rejects(
            r'spec/calibration/misplaced-acceptance-record\.json must be a calibration record',
            'an acceptance-purpose record must fail when loaded from the calibration directory',
        )

    def test_explicit_write_repairs_report_after_source_validation(self) -> None:
        """Limit a successful write request to the generated validation report."""
        self.report.write_text('{')
        before = self.source_bytes()
        self.assertEqual(self.run_main(['--write']), 0)
        after = self.source_bytes()
        self.assertEqual({key for key in before if before[key] != after[key]},
                         {'docs/validation-results.json'})
        self.assertEqual(json.loads(self.report.read_text())['status'], 'pass')
        self.assertEqual(self.run_main([]), 0)

    def test_cli_injects_evaluation_date_and_base_revision(self) -> None:
        """Pass CLI values into validation context and print the freeze summary."""
        observed: dict[str, object] = {}

        def freeze(context: ValidationContext, base_revision: str | None,
                   read_json_at_revision: RevisionJsonReader) -> str:
            """Capture command-line values and the composition-root reader."""
            observed['as_of'] = context.as_of
            observed['base_revision'] = base_revision
            observed['reader_is_callable'] = callable(read_json_at_revision)
            return 'Freeze check fixture passed.'

        stderr = io.StringIO()
        with patch.object(check_docs, 'check_frozen', side_effect=freeze), contextlib.redirect_stderr(stderr):
            result = self.run_main([
                '--write', '--as-of', '2026-10-15', '--base-rev', 'fixture-base',
            ])

        self.assertEqual(result, 0, 'the checker should accept an explicit evaluation date and base revision')
        self.assertEqual(observed, {
            'as_of': date(2026, 10, 15), 'base_revision': 'fixture-base',
            'reader_is_callable': True,
        }, 'the parsed CLI values must reach the context and freeze check')
        self.assertIn('Freeze check fixture passed.', stderr.getvalue(),
                      'the caller must see the summary returned by the freeze check')

    def test_cli_supplies_resolved_revision_to_the_check_composition(self) -> None:
        """Resolve Git identity in the command root before composing roadmap checks."""
        observed: dict[str, str | None] = {}

        def capture_context(context: ValidationContext) -> None:
            """Capture the revision passed to the composed check sequence."""
            observed['source_revision'] = context.source_revision

        with (patch.object(check_docs, 'git_head_revision', return_value='fixture-revision') as resolve_revision,
              patch.object(check_docs, 'collect_checks', side_effect=capture_context),
              patch.object(check_docs, 'check_frozen', return_value='Freeze check fixture passed.'),
              contextlib.redirect_stdout(io.StringIO())):
            result = self.run_main(['--write'])

        self.assertEqual(result, 0, 'composition should complete with an injected source revision')
        self.assertEqual(observed, {'source_revision': 'fixture-revision'},
                         'roadmap checks must receive the revision resolved by the application boundary')
        resolve_revision.assert_called_once_with(self.root)

    def test_cli_rejects_an_accepted_decision_edit_against_git_base(self) -> None:
        """Surface a real base-revision freeze failure through the command-line entrypoint."""
        accepted = {
            'id': 'D04', 'subject': 'Package licence', 'lifecycle': 'accepted',
            'decided_option': 'A', 'supersedes': [], 'superseded_by': None,
        }
        decisions = self.root / 'spec/decisions.json'
        decisions.write_text(json.dumps({'decisions': [accepted]}), encoding='utf-8')
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(['git', 'add', 'spec/decisions.json'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(
            ['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.org',
             '-c', 'commit.gpgsign=false', 'commit', '-q', '-m', 'Accept D04'],
            cwd=self.root, check=True, capture_output=True,
        )
        decisions.write_text(json.dumps({'decisions': [accepted | {'subject': 'Different licence'}]}),
                             encoding='utf-8')

        with patch.object(check_docs, 'collect_checks'), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, 'Accepted decision D04 was edited'):
                self.run_main(['--base-rev', 'HEAD'])


    def test_evidence_backed_completed_tasks_pass_the_full_checker(self):
        """Accept completed tasks backed by their committed closure evidence."""
        self.assertEqual(self.run_main([]), 0, 'supported completed tasks must pass the full checker')
        report = json.loads(self.report.read_text())
        closure = next(row for row in report['checks'] if row['check'] == 'roadmap-status')
        self.assertEqual(closure['count'], 4, 'all four completed acceptance-control tasks must be validated')
        self.assertEqual(closure['status'], 'pass', 'completion requires a passing evidence check')

    def test_completed_task_without_its_completion_record_fails_the_full_checker(self):
        """Reject unsupported completion without rewriting the committed report."""
        path = self.root / 'spec/task-completion.json'
        completion = json.loads(path.read_text())
        completion['tasks'] = [record for record in completion['tasks'] if record['task'] != '1.1.1']
        path.write_text(json.dumps(completion), encoding='utf-8')
        before = self.report.read_bytes()
        with self.assertRaisesRegex(SystemExit, 'Task 1.1.1 is ticked but no completion record'):
            self.run_main(['--write'])
        self.assertEqual(self.report.read_bytes(), before, 'rejected completion must not overwrite the report')

if __name__ == '__main__':
    unittest.main()
