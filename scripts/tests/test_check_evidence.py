"""Prove the evidence command reports gate levels and exits as documented."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from check_evidence import app

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tools/tests/fixtures/evidence'
EXAMPLE = ROOT / 'spec/proof-evidence.example.json'
WITH_PARSERS = ('--bindings', str(FIXTURES / 'bindings.json'), '--log-parsers', str(FIXTURES / 'log-parsers.json'))


def run(*args: str) -> int:
    """Invoke the Cyclopts entry point and return its exit code."""
    with pytest.raises(SystemExit) as exited:
        app(list(args))
    return exited.value.code


def fixture(name: str) -> str:
    """Return the path of one evidence fixture."""
    return str(FIXTURES / f'{name}.json')


def test_planned_example_is_rejected_as_not_run(capsys):
    assert run('--as-of', '2026-10-10', str(EXAMPLE)) == 1, 'a planned record falls short of tested'
    out = capsys.readouterr().out
    assert 'rejected [' in out and 'not-run' in out, 'the planned record names why it is rejected'


def test_complete_test_record_is_admitted_at_tested(capsys):
    assert run('--as-of', '2026-10-10', *WITH_PARSERS, fixture('complete-test')) == 0, 'tested meets the default'
    assert ': tested []' in capsys.readouterr().out


@pytest.mark.parametrize(('required', 'code'), [('bounded', 0), ('proof', 1)])
def test_partial_bounds_reach_bounded_but_never_proof(required, code, capsys):
    assert run('--as-of', '2026-10-10', '--require', required, *WITH_PARSERS, fixture('partial-bounds-kani')) == code
    assert ': bounded []' in capsys.readouterr().out, 'partial bounds are reported as bounded'


@pytest.mark.parametrize(('name', 'reason'), [('resource-exhausted-kani', 'outcome-resource-exhausted'),
                                              ('self-reported-verus', 'verdict-self-reported')])
def test_failing_records_are_rejected_with_their_reason(name, reason, capsys):
    assert run('--as-of', '2026-10-10', *WITH_PARSERS, fixture(name)) == 1, f'{name} must fall short'
    assert f'rejected [{reason}]' in capsys.readouterr().out


def test_without_a_registered_parser_a_verifier_verdict_is_self_reported(capsys):
    assert run('--as-of', '2026-10-10', '--bindings', str(FIXTURES / 'bindings.json'),
               fixture('partial-bounds-kani')) == 1, 'the repository registers no parser yet (C-EP-10)'
    assert 'verdict-self-reported' in capsys.readouterr().out


def test_schema_invalid_record_exits_two(tmp_path, capsys):
    record = json.loads(EXAMPLE.read_text(encoding='utf-8'))
    record['outcome'] = 'verified'
    path = tmp_path / 'invalid.json'
    path.write_text(json.dumps(record), encoding='utf-8')
    assert run('--as-of', '2026-10-10', str(path)) == 2, 'a record breaking the validity predicate is schema-invalid'
    assert 'schema-invalid' in capsys.readouterr().err


def test_every_record_is_reported_even_after_an_invalid_one(tmp_path, capsys):
    broken = tmp_path / 'broken.json'
    broken.write_text('{not json', encoding='utf-8')
    missing = tmp_path / 'missing.json'
    code = run('--as-of', '2026-10-10', *WITH_PARSERS, str(broken), str(missing), fixture('complete-test'))
    captured = capsys.readouterr()
    assert code == 2, 'unreadable input exits 2'
    assert 'broken.json: unreadable' in captured.err, 'malformed JSON is reported as unreadable'
    assert 'missing.json: unreadable' in captured.err, 'a missing file is reported as unreadable'
    assert ': tested []' in captured.out, 'records after an invalid one are still admitted and reported'


@pytest.mark.parametrize('args', [('--as-of', 'yesterday', str(EXAMPLE)), ('--as-of', '2026-10-10', '--require',
                                                                             'restricted', str(EXAMPLE))])
def test_usage_errors_exit_two(args, capsys):
    assert run(*args) == 2, 'bad dates and unsatisfiable requirements are usage errors'
    assert 'usage error' in capsys.readouterr().err


def test_as_of_can_come_from_the_environment(monkeypatch, capsys):
    monkeypatch.setenv('INPUT_AS_OF', '2026-10-10')
    assert run(*WITH_PARSERS, fixture('complete-test')) == 0, 'INPUT_AS_OF supplies the date in CI'
