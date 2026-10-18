"""Keep the Design contracts workflow and Make invocation wired together."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class WorkflowEvent:
    """Inputs supplied by one checked GitHub workflow event in this test module."""

    name: str
    before: str
    base_sha: str


class DesignWorkflowContract(unittest.TestCase):
    """Check that workflow-selected inputs reach the reproducible design check."""

    def _make_python_recorder(self, directory: Path) -> Path:
        """Create a Python command stub that records Make's actual arguments."""
        script = directory / 'python-recorder'
        script.write_text(
            f'#!{sys.executable}\n'
            'import json\n'
            'import os\n'
            'import sys\n'
            'with open(os.environ["PYTHON_ARGUMENT_LOG"], "a", encoding="utf-8") as log:\n'
            '    log.write(json.dumps(sys.argv[1:]) + "\\n")\n',
            encoding='utf-8',
        )
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return script

    def _run_make_design_check(
        self,
        python_recorder: Path,
        argument_log: Path,
        base_revision: str,
        as_of: str | None,
    ) -> list[list[str]]:
        """Run the Make target while recording its expanded Python commands."""
        argument_log.unlink(missing_ok=True)
        command = [
            'make', '--no-print-directory', 'design-check',
            f'PYTHON={python_recorder}', f'BASE_REV={base_revision}',
        ]
        if as_of is not None:
            command.append(f'AS_OF={as_of}')
        environment = os.environ.copy()
        environment.pop('AS_OF', None)
        environment['PYTHON_ARGUMENT_LOG'] = str(argument_log)
        subprocess.run(
            command, cwd=ROOT, env=environment,
            check=True, capture_output=True, text=True,
        )
        lines = argument_log.read_text(encoding='utf-8').splitlines()
        return cast('list[list[str]]', [json.loads(line) for line in lines])

    def _workflow_base_step(self) -> str:
        """Return the executable base-selection step from the checked workflow."""
        workflow = yaml.load(
            (ROOT / '.github/workflows/design.yml').read_text(encoding='utf-8'),
            Loader=yaml.BaseLoader,
        )
        steps = workflow['jobs']['design-check']['steps']
        base_step = next(step for step in steps if step.get('id') == 'base')
        return cast('str', base_step['run'])

    def _run_git(self, repository: Path, *arguments: str) -> str:
        """Run Git in a fixture repository and return its standard output."""
        result = subprocess.run(
            ['git', *arguments], cwd=repository,
            check=True, capture_output=True, text=True,
        )
        return result.stdout.strip()

    def _make_git_fixture(self, repository: Path) -> tuple[str, str]:
        """Create base and head commits plus the remote-tracking base ref."""
        repository.mkdir()
        self._run_git(repository, 'init', '--quiet')
        self._run_git(repository, 'checkout', '--quiet', '-b', 'main')
        self._run_git(repository, 'config', 'user.name', 'Workflow Contract Test')
        self._run_git(repository, 'config', 'user.email', 'workflow@example.invalid')
        source = repository / 'contract.txt'
        source.write_text('base\n', encoding='utf-8')
        self._run_git(repository, 'add', 'contract.txt')
        self._run_git(repository, 'commit', '--quiet', '-m', 'base')
        base_revision = self._run_git(repository, 'rev-parse', 'HEAD')
        self._run_git(
            repository, 'update-ref', 'refs/remotes/origin/main', base_revision,
        )
        self._run_git(repository, 'checkout', '--quiet', '-b', 'feature')
        source.write_text('feature\n', encoding='utf-8')
        self._run_git(repository, 'commit', '--quiet', '-am', 'feature')
        head_revision = self._run_git(repository, 'rev-parse', 'HEAD')
        return base_revision, head_revision

    def _run_workflow_base_step(
        self,
        repository: Path,
        date_command: Path,
        event: WorkflowEvent,
    ) -> dict[str, str]:
        """Execute the checked workflow with fixture refs and capture outputs."""
        script = self._workflow_base_step()
        output = repository.parent / 'github-output'
        output.unlink(missing_ok=True)
        environment = os.environ.copy()
        environment.update({
            'BASE_SHA': event.base_sha,
            'BEFORE': event.before,
            'EVENT': event.name,
            'GITHUB_OUTPUT': str(output),
            'PATH': os.pathsep.join((str(date_command.parent), environment['PATH'])),
        })
        subprocess.run(
            ['bash', '--noprofile', '--norc', '-e', '-o', 'pipefail', '-c', script],
            cwd=repository, env=environment,
            check=True, capture_output=True, text=True,
        )
        return dict(
            line.partition('=')[::2]
            for line in output.read_text(encoding='utf-8').splitlines()
        )

    def test_workflow_passes_base_and_scheduled_date_to_make(self) -> None:
        """Preserve full history and connect selected workflow outputs to Make."""
        workflow = yaml.load(
            (ROOT / '.github/workflows/design.yml').read_text(encoding='utf-8'),
            Loader=yaml.BaseLoader,
        )
        checkout = workflow['jobs']['design-check']['steps'][0]
        self.assertEqual(checkout['with']['fetch-depth'], '0',
                         'freeze checks need the merge base in checkout history')

        steps = workflow['jobs']['design-check']['steps']
        base_step = next(step for step in steps if step.get('id') == 'base')
        self.assertIn('git merge-base "$BASE_SHA" HEAD', base_step['run'],
                      'pull requests must compare frozen decisions with the event base commit')
        self.assertIn('date -u +%F', base_step['run'],
                      'scheduled expiry checks must use the workflow run date')

        check_step = next(step for step in steps if step.get('name') == 'Validate documentation contracts')
        self.assertEqual(check_step['env']['BASE_REV'], '${{ steps.base.outputs.rev }}',
                         'the selected revision must reach Make as BASE_REV')
        self.assertEqual(check_step['env']['RUN_DATE'], '${{ steps.base.outputs.as_of }}',
                         'the scheduled date must reach Make as RUN_DATE')
        self.assertIn('make design-check BASE_REV="$BASE_REV"', check_step['run'],
                      'the workflow must invoke the Make target with its base revision')
        self.assertIn('AS_OF="$RUN_DATE"', check_step['run'],
                      'the workflow must pass a scheduled evaluation date')

    def test_make_forwards_as_of_and_base_revision_to_checker(self) -> None:
        """Exercise Make expansion for empty and populated base revisions."""
        with tempfile.TemporaryDirectory(prefix='design-check-make-') as directory_name:
            directory = Path(directory_name)
            recorder = self._make_python_recorder(directory)
            for base_revision in ('', 'fixture-base'):
                with self.subTest(base_revision=base_revision):
                    calls = self._run_make_design_check(
                        recorder, directory / 'arguments.jsonl',
                        base_revision, '2026-10-15',
                    )
                    expected = ['tools/check_docs.py', '--as-of', '2026-10-15']
                    if base_revision:
                        expected.extend(('--base-rev', base_revision))
                    self.assertEqual(
                        calls[0], expected,
                        'Make must pass the fixed date and only a populated base revision',
                    )
                    self.assertEqual(
                        calls[1:], [
                            ['-m', 'unittest', 'discover', '-s', 'tools/tests'],
                            ['-m', 'pytest', '-q', 'scripts/tests'],
                        ],
                        'Make must continue to run both design-check test suites',
                    )

    def test_make_defaults_as_of_to_the_head_commit_date(self) -> None:
        """Use the selected repository HEAD date when AS_OF is not supplied."""
        head_date = subprocess.run(
            ['git', 'log', '-1', '--format=%cs', 'HEAD'],
            cwd=ROOT, check=True, capture_output=True, text=True,
        ).stdout.strip()
        with tempfile.TemporaryDirectory(prefix='design-check-date-') as directory_name:
            directory = Path(directory_name)
            calls = self._run_make_design_check(
                self._make_python_recorder(directory),
                directory / 'arguments.jsonl', '', None,
            )
        self.assertEqual(
            calls[0], ['tools/check_docs.py', '--as-of', head_date],
            'Make must derive its default evaluation date from HEAD',
        )

    def test_workflow_selects_base_and_date_for_each_event(self) -> None:
        """Execute the workflow selector against fixture Git refs."""
        with tempfile.TemporaryDirectory(prefix='design-check-workflow-') as directory_name:
            directory = Path(directory_name)
            repository = directory / 'repository'
            base_revision, _ = self._make_git_fixture(repository)
            date_command = directory / 'bin' / 'date'
            date_command.parent.mkdir()
            date_command.write_text(
                f'#!{sys.executable}\nprint("2031-02-03")\n', encoding='utf-8',
            )
            date_command.chmod(
                date_command.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
            )
            cases = (
                (WorkflowEvent('pull_request', '', base_revision), base_revision, ''),
                (WorkflowEvent('push', base_revision, ''), base_revision, ''),
                (WorkflowEvent('push', 'missing-revision', ''), '', ''),
                (WorkflowEvent('push', '', ''), '', ''),
                (WorkflowEvent('schedule', '', ''), '', '2031-02-03'),
                (WorkflowEvent('workflow_dispatch', '', ''), '', ''),
            )
            for event, expected_revision, expected_date in cases:
                with self.subTest(event=event.name, before=event.before):
                    outputs = self._run_workflow_base_step(
                        repository, date_command, event,
                    )
                    self.assertEqual(
                        outputs,
                        {'rev': expected_revision, 'as_of': expected_date},
                        f'{event} must select the expected base and evaluation date',
                    )

    def test_pull_request_fails_when_merge_base_is_missing(self) -> None:
        """Fail before writing an empty freeze base when the base ref is absent."""
        with tempfile.TemporaryDirectory(prefix='design-check-missing-base-') as directory_name:
            directory = Path(directory_name)
            repository = directory / 'repository'
            self._make_git_fixture(repository)
            date_command = directory / 'date'
            date_command.write_text(f'#!{sys.executable}\nprint("2031-02-03")\n', encoding='utf-8')
            date_command.chmod(
                date_command.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
            )
            with self.assertRaises(
                subprocess.CalledProcessError,
                msg='the pull-request selector must fail when Git cannot find a merge base',
            ):
                self._run_workflow_base_step(
                    repository, date_command,
                    WorkflowEvent('pull_request', '', 'missing-base-revision'),
                )

            self.assertFalse(
                (repository.parent / 'github-output').exists(),
                'the failed merge-base lookup must not write an empty freeze revision',
            )


if __name__ == '__main__':
    unittest.main()
