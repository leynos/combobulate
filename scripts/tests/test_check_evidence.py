"""Prove the evidence command reports gate levels and exits as documented."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from check_evidence import app

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tools/tests/fixtures/evidence'
EXAMPLE = ROOT / 'spec/proof-evidence.example.json'
WITH_BINDINGS = ('--bindings', str(FIXTURES / 'bindings.json'),)


def run(*args: str) -> int:
    """Invoke the Cyclopts entry point and return its exit code."""
    with pytest.raises(SystemExit) as exited:
        app(list(args))
    return exited.value.code


def fixture(name: str) -> str:
    """Return the path of one evidence fixture."""
    return str(FIXTURES / f'{name}.json')


def test_planned_example_reports_all_blocking_reasons(capsys):
    """Report every blocking reason for the committed planned example."""
    assert run('--as-of', '2026-10-10', str(EXAMPLE)) == 1, 'a planned record falls short of tested'
    out = capsys.readouterr().out
    assert out.splitlines() == [
        f'{EXAMPLE}: rejected [witness-absent, control-required-missing, binding-incomplete, not-run]',
    ], 'the planned record reports all blocking reasons in rule order'


def test_standalone_entrypoint_has_its_runtime_dependencies():
    """Run the PEP 723 entry point with only its declared script dependencies."""
    result = subprocess.run(
        [
            str(ROOT / 'scripts/check_evidence.py'),
            '--as-of',
            '2026-10-10',
            *WITH_BINDINGS,
            fixture('complete-test'),
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f'standalone CLI should admit tested evidence: {result.stderr}'
    assert result.stdout.splitlines() == [
        f"{fixture('complete-test')}: tested []",
    ], 'standalone CLI reports the admitted level and reasons'


def test_complete_test_record_is_admitted_at_tested(capsys):
    """Accept complete test evidence at the CLI's default minimum level."""
    assert run('--as-of', '2026-10-10', *WITH_BINDINGS, fixture('complete-test')) == 0, 'tested meets the default'
    assert ': tested []' in capsys.readouterr().out


@pytest.mark.parametrize('required', ['bounded', 'proof'])
def test_partial_bounds_stay_self_reported_without_a_parser_adapter(required, capsys):
    """Keep verifier claims below bounded until an adapter verifies their cited log."""
    assert run('--as-of', '2026-10-10', '--require', required, *WITH_BINDINGS,
               fixture('partial-bounds-kani')) == 1, 'tool registration alone cannot satisfy a proof level'
    assert ': rejected [verdict-self-reported]' in capsys.readouterr().out


@pytest.mark.parametrize(('name', 'reason'), [('resource-exhausted-kani', 'outcome-resource-exhausted'),
                                              ('self-reported-verus', 'verdict-self-reported')])
def test_failing_records_are_rejected_with_their_reason(name, reason, capsys):
    """Report the specific reason for an outcome or verdict-source failure."""
    assert run('--as-of', '2026-10-10', *WITH_BINDINGS, fixture(name)) == 1, f'{name} must fall short'
    assert reason in capsys.readouterr().out, f'{name} names {reason}'


def test_without_a_registered_parser_a_verifier_verdict_is_self_reported(capsys):
    """Fail closed when the CLI has no verified adapter result for a log claim."""
    assert run('--as-of', '2026-10-10', '--bindings', str(FIXTURES / 'bindings.json'),
               fixture('partial-bounds-kani')) == 1, 'the repository registers no parser yet (C-EP-10)'
    assert 'verdict-self-reported' in capsys.readouterr().out


def test_parser_registry_cannot_be_supplied_by_the_caller(capsys):
    """Prevent CLI callers from turning a tool-name list into parser authority."""
    code = run('--as-of', '2026-10-10', '--log-parsers', str(ROOT / 'spec/evidence-reason-codes.json'),
               '--bindings', str(FIXTURES / 'bindings.json'), fixture('partial-bounds-kani'))
    assert code == 2, 'parser registration is controlled by repository policy and adapter integration'
    assert '--log-parsers' in capsys.readouterr().err, 'the CLI rejects a caller-supplied parser registry'


def test_schema_invalid_record_exits_two(tmp_path, capsys):
    """Return the schema-invalid exit code for a record that breaks the validity predicate."""
    record = json.loads(EXAMPLE.read_text(encoding='utf-8'))
    record['outcome'] = 'verified'
    path = tmp_path / 'invalid.json'
    path.write_text(json.dumps(record), encoding='utf-8')
    assert run('--as-of', '2026-10-10', str(path)) == 2, 'a record breaking the validity predicate is schema-invalid'
    assert 'schema-invalid' in capsys.readouterr().err


@pytest.mark.parametrize(('field', 'value'), [('schema_version', 1), ('undocumented_field', 'rejected')])
def test_legacy_version_and_unknown_property_exit_two(field, value, tmp_path, capsys):
    """Reject legacy schema versions and unknown fields at the command boundary."""
    record = json.loads((FIXTURES / 'complete-test.json').read_text(encoding='utf-8'))
    record[field] = value
    path = tmp_path / 'invalid-schema.json'
    path.write_text(json.dumps(record), encoding='utf-8')

    assert run('--as-of', '2026-10-10', str(path)) == 2, 'invalid schema records exit two'
    assert 'schema-invalid' in capsys.readouterr().err, 'the CLI identifies the schema failure'


def test_no_record_arguments_exit_two(capsys):
    """Require at least one evidence record instead of reporting an empty success."""
    assert run('--as-of', '2026-10-10') == 2, 'an invocation without records is a usage error'
    assert 'give at least one record' in capsys.readouterr().err, 'the usage diagnostic explains the missing input'


@pytest.mark.parametrize('option', ['--bindings', '--exceptions', '--decisions', '--roadmap'])
def test_unreadable_configuration_exits_two(option, tmp_path, capsys):
    """Treat missing registries as configuration errors without emitting a traceback."""
    missing = str(tmp_path / 'missing.json')
    settings = {'--bindings': str(FIXTURES / 'bindings.json'),
                '--exceptions': str(ROOT / 'spec/exceptions.json'),
                '--decisions': str(ROOT / 'spec/decisions.json'), '--roadmap': str(ROOT / 'spec/roadmap.json')}
    settings[option] = missing
    arguments = ['--as-of', '2026-10-10']
    for name, path in settings.items():
        arguments.extend((name, path))
    arguments.append(fixture('complete-test'))

    assert run(*arguments) == 2, 'an unreadable configuration is a usage error'
    error = capsys.readouterr().err
    assert 'usage error: cannot load configuration' in error, 'configuration failures have a usage diagnostic'
    assert 'Traceback' not in error, 'configuration failures do not leak a traceback'


@pytest.mark.parametrize(('document', 'kind'), [('[]', 'array'), ('null', 'null')], ids=['array', 'null'])
def test_non_object_bindings_configuration_exits_two(document, kind, tmp_path, capsys):
    """Reject binding configuration documents that are not component maps."""
    bindings = tmp_path / 'bindings.json'
    bindings.write_text(document, encoding='utf-8')

    assert run('--as-of', '2026-10-10', '--bindings', str(bindings), fixture('complete-test')) == 2, \
        f'a JSON {kind} cannot be used as a bindings map'
    error = capsys.readouterr().err
    assert 'usage error: cannot load configuration' in error, 'invalid bindings have a usage diagnostic'
    assert 'must contain a JSON object' in error, 'the diagnostic explains the bindings shape'
    assert 'Traceback' not in error, 'invalid bindings do not leak a traceback'


def test_every_record_is_reported_even_after_an_invalid_one(tmp_path, capsys):
    """Continue reporting later records while preserving the invalid-input exit code."""
    broken = tmp_path / 'broken.json'
    broken.write_text('{not json', encoding='utf-8')
    missing = tmp_path / 'missing.json'
    code = run('--as-of', '2026-10-10', *WITH_BINDINGS, str(broken), str(missing), fixture('complete-test'))
    captured = capsys.readouterr()
    assert code == 2, 'unreadable input exits 2'
    assert 'broken.json: unreadable' in captured.err and 'missing.json: unreadable' in captured.err
    assert ': tested []' in captured.out, 'records after an invalid one are still admitted and reported'


@pytest.mark.parametrize('args', [('--as-of', 'yesterday', str(EXAMPLE)), ('--as-of', '2026-10-10', '--require',
                                                                             'restricted', str(EXAMPLE))])
def test_usage_errors_exit_two(args, capsys):
    """Report malformed dates and unsupported minimum levels as usage errors."""
    assert run(*args) == 2, 'bad dates and unsatisfiable requirements are usage errors'
    assert 'usage error' in capsys.readouterr().err


def test_as_of_can_come_from_the_environment(monkeypatch, capsys):
    """Accept the injected CI evaluation date without reading the wall clock."""
    monkeypatch.setenv('INPUT_AS_OF', '2026-10-10')
    assert run(*WITH_BINDINGS, fixture('complete-test')) == 0, 'INPUT_AS_OF supplies the date in CI'


@pytest.mark.parametrize(('sponsor', 'status', 'expected'), [
    ('alternate-sponsor', 'open', []),
    ('different-sponsor', 'open', ['approver-not-sponsor']),
    ('alternate-sponsor', 'done', ['past-release-gate']),
])
def test_exception_policy_uses_explicit_decision_and_roadmap_paths(sponsor, status, expected, tmp_path, capsys):
    """Load injected sponsor authority and release-gate completion through CLI options."""
    from check_evidence import exception_register

    entry = {'id': 'EXC-0001', 'component': 'PF09.proof@2.4.1', 'owner': 'owner',
             'approved_by': 'alternate-sponsor', 'approved_on': '2026-10-01', 'invalid_from': '2026-11-01',
             'narrowed_claim': 'Only small inputs.', 'release_gate': '4.3.3'}
    documents = {
        '--exceptions': {'exceptions': [entry]},
        '--decisions': {'authorities': {'roles': {'sponsor': sponsor}}},
        '--roadmap': {'phases': [{'steps': [{'tasks': [{'id': '4.3.3', 'status': status}]}]}]},
    }
    arguments = ['--as-of', '2026-10-10', *WITH_BINDINGS]
    paths = {}
    for option, document in documents.items():
        path = tmp_path / f'{option[2:]}.json'
        path.write_text(json.dumps(document), encoding='utf-8')
        paths[option] = path
        arguments.extend((option, str(path)))
    register = exception_register(paths['--exceptions'], paths['--decisions'], paths['--roadmap'])
    assert register['EXC-0001']['problems'] == expected, 'injected authority and release gate determine D02 problems'
    assert run(*arguments, fixture('complete-test')) == 0, 'explicit policy paths are accepted by the public CLI'
    assert ': tested []' in capsys.readouterr().out, 'alternate policy files preserve unrelated test admission'
