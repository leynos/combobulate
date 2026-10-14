"""Offline behavioural probes for upstream Whitaker validation/run fragments.

Only two named shell fragments run, with synthetic inputs, a fake installer,
private paths and controlled utility executors. This is a capability check,
not a security sandbox or proof of every composite-action step.
"""
from __future__ import annotations

import dataclasses
import os
import signal
import subprocess
import tempfile
from pathlib import Path

PROBE_TIMEOUT_SECONDS = 5
INSTALLER_STUB = '''#!/bin/bash
set -eu
printf '%s\\n' "$@" > "$PROBE_ROOT/arguments"
if [ "$PROBE_MISSING_ASSET" = true ]; then
  case " $* " in
    *' --no-source-fallback '*) echo 'source fallback is forbidden' >&2; exit 42 ;;
    *) touch "$PROBE_ROOT/cargo-started"; exit 0 ;;
  esac
fi
printf '%s' "$PROBE_STDOUT"
printf '%s' "$PROBE_STDERR" >&2
exit "$PROBE_STATUS"
'''
DENIED_EXECUTOR = '''#!/bin/bash
printf '%s\\n' "$0" >> "$PROBE_ROOT/denied-command"
exit 95
'''


@dataclasses.dataclass(frozen=True)
class Scenario:
    """The installer inputs, output streams and return status for one probe."""

    cranelift: str = 'false'
    ci_mode: str = 'true'
    stdout: str = 'prebuilt installed\n'
    stderr: str = ''
    status: int = 0
    missing_asset: bool = False
    suite_version: str = ''
    installer_version: str | None = None


def require(condition: bool, message: str) -> None:
    """Reject an unmet capability; e.g. a successful source fallback is an error."""
    if not condition:
        raise ValueError(message)


def fragments(manifest: dict) -> tuple[dict, dict, dict]:
    """Select unique unguarded Bash boundaries and the action's own input defaults."""
    require(manifest.get('runs', {}).get('using') == 'composite', 'Whitaker must be composite')
    selected = []
    for name in ('Validate Whitaker inputs', 'Run Whitaker installer'):
        matches = [step for step in manifest['runs']['steps'] if step.get('name') == name]
        require(len(matches) == 1, f'exactly one {name} boundary must exist')
        step = matches[0]
        require(step.get('shell') == 'bash' and isinstance(step.get('run'), str),
                f'{name} must expose a Bash fragment')
        require('if' not in step and 'continue-on-error' not in step,
                f'{name} cannot be skipped or softened')
        selected.append(step)
    inputs = manifest['inputs']
    require('cranelift' in inputs, 'the action must support the Cranelift input')
    return selected[0], selected[1], inputs


def input_values(inputs: dict, scenario: Scenario, root: Path) -> dict[str, str]:
    """Use action defaults, changing only the explicit scenario's input variables."""
    defaults = {name: item.get('default', '') for name, item in inputs.items()}
    require(all(isinstance(value, str) for value in defaults.values()), 'input defaults must be text')
    return {**defaults, 'cargo-home': str(root / 'cargo-home'), 'ci-mode': scenario.ci_mode,
            'cranelift': scenario.cranelift, 'suite-version': scenario.suite_version,
            'installer-version': scenario.installer_version or defaults['installer-version']}


def executable(path: Path, source: str) -> None:
    """Write a private fake command; e.g. denied download tools record and fail."""
    path.write_text(source, encoding='utf-8')
    path.chmod(0o700)


def environment(root: Path, values: dict, scenario: Scenario) -> dict[str, str]:
    """Create an explicit child environment without credentials or ambient tool paths."""
    tools = root / 'utilities'
    tools.mkdir()
    for command in ('mkdir', 'tr', 'tee', 'cat', 'grep', 'touch'):
        origin = Path('/usr/bin') / command
        require(origin.is_file(), f'probe utility unavailable: {origin}')
        (tools / command).symlink_to(origin)
    for command in ('curl', 'wget', 'git', 'cargo', 'rustup', 'python', 'python3', 'node', 'uv'):
        executable(tools / command, DENIED_EXECUTOR)
    installer = root / 'cargo-home' / 'bin' / 'whitaker-installer'
    installer.parent.mkdir(parents=True)
    executable(installer, INSTALLER_STUB)
    (root / 'output').touch()
    (root / 'path').touch()
    (root / 'summary').touch()
    return {'PATH': str(tools), 'HOME': str(root / 'home'), 'CARGO_HOME': str(root / 'cargo-home'),
            'RUNNER_TEMP': str(root), 'RUNNER_OS': 'Linux', 'GITHUB_OUTPUT': str(root / 'output'),
            'GITHUB_PATH': str(root / 'path'), 'GITHUB_STEP_SUMMARY': str(root / 'summary'),
            'PROBE_ROOT': str(root), 'PROBE_STDOUT': scenario.stdout, 'PROBE_STDERR': scenario.stderr,
            'PROBE_STATUS': str(scenario.status), 'PROBE_MISSING_ASSET': str(scenario.missing_asset).lower(),
            'WHITAKER_INSTALLER_PATH': str(installer), 'WHITAKER_INSTALLER_VERSION': values['installer-version']}


def resolve_env(step: dict, values: dict, base: dict) -> dict[str, str]:
    """Resolve the limited input/output expressions the probed fragments consume."""
    result = dict(base)
    for name, expression in step.get('env', {}).items():
        if isinstance(expression, str) and expression.startswith('${{ inputs.'):
            input_name = expression.removeprefix('${{ inputs.').removesuffix(' }}')
            require(input_name in values, f'unknown action input: {input_name}')
            result[name] = values[input_name]
        elif expression == '${{ steps.validate-inputs.outputs.installer-path }}':
            result[name] = base['WHITAKER_INSTALLER_PATH']
        elif expression == '${{ steps.validate-inputs.outputs.installer-version }}':
            result[name] = values['installer-version']
        else:
            raise ValueError(f'unsupported probe environment expression: {name}={expression}')
    return result


def execute(step: dict, root: Path, env: dict) -> subprocess.CompletedProcess:
    """Run a bounded child process and kill its process group if a fragment stalls."""
    command = ['/bin/bash', '-Eeuo', 'pipefail', '-c', step['run']]
    with subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, start_new_session=True) as process:
        try:
            stdout, stderr = process.communicate(timeout=PROBE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise ValueError('capability fragment exceeded its execution time budget') from None
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def run_scenario(parts: tuple, scenario: Scenario, expectation: str) -> None:
    """Drive one source-derived lifecycle and compare actual effects with its contract."""
    validation, installation, inputs = parts
    with tempfile.TemporaryDirectory(prefix='combobulate-whitaker-probe-') as directory:
        root = Path(directory)
        values = input_values(inputs, scenario, root)
        base = environment(root, values, scenario)
        validated = execute(validation, root, resolve_env(validation, values, base))
        if expectation == 'invalid-input':
            require(validated.returncode != 0, 'prohibited installer/suite input was accepted')
            require(not any((root / name).exists() for name in
                            ('arguments', 'cargo-started', 'denied-command')),
                    'invalid inputs must fail before installation/download/build executors')
            return
        require(validated.returncode == 0, f'action defaults/inputs rejected: {validated.stderr}')
        outputs = dict(line.split('=', 1) for line in (root / 'output').read_text().splitlines())
        require(outputs.get('installer-path') == base['WHITAKER_INSTALLER_PATH'],
                'validation must select the configured private installer path')
        require(outputs.get('installer-version') == values['installer-version'],
                'validation must preserve the requested installer version')
        result = execute(installation, root, resolve_env(installation, values, base))
        require(not (root / 'denied-command').exists(), 'fragment attempted a network/build executor')
        require(not (root / 'cargo-started').exists(), 'missing assets permitted a source build')
        arguments = (root / 'arguments').read_text().splitlines() if (root / 'arguments').exists() else []
        expected_args = ['--no-source-fallback'] + (['--cranelift'] if scenario.cranelift == 'true' else [])
        require(arguments == expected_args, f'installer arguments violate binary-only policy: {arguments}')
        if expectation == 'success':
            require(result.returncode == 0, f'prebuilt route failed: {result.stderr}')
        else:
            require(result.returncode != 0, f'{expectation} was accepted as successful')


def probe_manifest(manifest: dict) -> int:
    """Verify both flag arms, refusal boundaries, fallback streams and cold asset failure."""
    parts = fragments(manifest)
    scenarios = [
        (Scenario(cranelift='true'), 'success'), (Scenario(), 'success'),
        (Scenario(ci_mode='false'), 'success'),
        (Scenario(status=43), 'installer-failure'),
        (Scenario(stdout='Installing whitaker lints from source\n'), 'source-stdout'),
        (Scenario(stderr='Installed cargo-dylint from source with cargo install.\n'), 'source-stderr'),
        (Scenario(ci_mode='false', stderr='Installed cargo-dylint from source with cargo install.\n'), 'source-stderr'),
        (Scenario(ci_mode='false', stdout='Installing whitaker lints from source\n'), 'source-stdout'),
        (Scenario(missing_asset=True), 'cold-missing-artifact'),
        (Scenario(installer_version='0.2.8'), 'invalid-input'),
        (Scenario(suite_version='main'), 'invalid-input'),
        (Scenario(suite_version='a' * 40, ci_mode='false'), 'invalid-input'),
    ]
    for scenario, expectation in scenarios:
        run_scenario(parts, scenario, expectation)
    return len(scenarios)
