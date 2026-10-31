"""Validate pre-registered acceptance controls and their measurement records (ADR-0008).

A control defines everything that decides its result before any acceptance
measurement exists: workload, metric, thresholds, environment and calibration.
Git history is the record of a change to it. Outcomes map so that budget
overruns, exhausted resources, and missing records never pass, and calibration
records never count as acceptance evidence (VO-12). Records describe hardware by
class only, never by host name or home path (VO-16).
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping

from jsonschema import Draft202012Validator

from .acceptance_evidence import (
    check_calibration_record, check_calibration_reference, check_control_bindings, check_measurement_binding,
    verdict,
)
from .acceptance_registration import FROZEN_FIELDS, check_completeness, check_registration_declarations
from .ci_controls import (
    OUTCOME_VERDICTS, AcceptanceWorkflowSettings, check_acceptance_workflow, check_ci_calibration,
    check_ci_measurement,
)
from .context import ValidationContext, require

__all__ = [
    'AcceptanceWorkflowSettings', 'FROZEN_FIELDS', 'OUTCOME_VERDICTS', 'check_acceptance_controls',
    'check_acceptance_workflow', 'check_calibration_record',
    'check_calibration_reference', 'check_ci_calibration', 'check_ci_measurement', 'check_completeness',
    'check_control_bindings', 'check_host_identity', 'check_measurement_binding', 'check_registration_declarations',
    'verdict',
]

HOST_PATTERNS = (re.compile(r'/home/'), re.compile(r'/Users/'))


def _workflow_settings(workflow: object) -> AcceptanceWorkflowSettings:
    """Adapt parsed CI YAML into AC-07 values; e.g. extract image and job timeout."""
    jobs = workflow.get('jobs', {}) if isinstance(workflow, Mapping) else {}
    job = jobs.get('build-test') if isinstance(jobs, Mapping) else None
    return AcceptanceWorkflowSettings(
        runner_image=job.get('runs-on') if isinstance(job, Mapping) else None,
        timeout_minutes=job.get('timeout-minutes') if isinstance(job, Mapping) else None,
    )


def check_host_identity(name: str, text: str, extra_names: Iterable[str] = ()) -> None:
    """Reject host paths and supplied host names in serialized evidence.

    Parameters
    ----------
    name : str
        Artefact name used in any diagnostic.
    text : str
        Serialized artefact content to scan before parsing.
    extra_names : Iterable[str], optional
        Host names supplied by the caller.

    Returns
    -------
    None
        Returns only when the content contains no prohibited identity.

    Raises
    ------
    AssertionError
        If the content contains a home path or supplied host name.

    Examples
    --------
    check_host_identity(name, '{"hardware": "Ubuntu 24.04"}') accepts a host class.
    """
    for pattern in HOST_PATTERNS:
        require(pattern.search(text) is None, f'{name} contains a home path')
    for value in extra_names:
        require(not value or value not in text, f'{name} contains host identity {value!r}')


def _iter_decoded_json_strings(value: object) -> Iterable[str]:
    """Yield JSON object keys and string values recursively; e.g. from nested records.

    Examples
    --------
    list(_iter_decoded_json_strings({'hardware': ['runner', {'class': 'ubuntu'}]}))
    yields ['hardware', 'runner', 'class', 'ubuntu'].
    """
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                yield key
            yield from _iter_decoded_json_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_decoded_json_strings(item)


def _load_identity_checked_json(name: str, text: str, extra_names: Iterable[str]) -> object:
    """Reject identities in raw and decoded JSON; e.g. catch escaped home paths.

    Examples
    --------
    _load_identity_checked_json('record.json', '{"command": "verus"}', ())
    returns a parsed record after checking its serialized and decoded strings.
    """
    check_host_identity(name, text, extra_names)
    record = json.loads(text)
    for decoded_string in _iter_decoded_json_strings(record):
        check_host_identity(name, decoded_string, extra_names)
    return record





def check_acceptance_controls(context: ValidationContext, extra_names: Iterable[str] = ()) -> None:
    """Validate the control register, its calibration records, and the calibration report.

    Parameters
    ----------
    context : ValidationContext
        Repository inputs and results owned by the documentation checker.
    extra_names : Iterable[str], optional
        Additional host names supplied by the caller for identity scans.

    Returns
    -------
    None
        Records the acceptance-control validation result in the context.

    Raises
    ------
    AssertionError
        If a register, calibration record, or measurement violates a rule.
    jsonschema.ValidationError
        If a control or measurement does not match its schema.
    ValueError
        If the workflow YAML is malformed.
    OSError
        If a register, schema, calibration record, measurement record, or
        calibration report cannot be read.

    Examples
    --------
    check_acceptance_controls(context) records a passing check for a valid register.
    """
    extra_names = tuple(extra_names)
    register = context.load('spec/acceptance-controls.json')
    Draft202012Validator(
        context.load('spec/acceptance-controls.schema.json'),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    ).validate(register)
    check_registration_declarations(register)
    record_schema = Draft202012Validator(context.load('spec/measurement-record.schema.json'),
                                         format_checker=Draft202012Validator.FORMAT_CHECKER)
    records = _load_calibration_records(context, record_schema, extra_names)
    measurements = _load_acceptance_measurements(context, record_schema, extra_names)
    report = context.root / 'docs/acceptance-calibration.md'
    check_host_identity('docs/acceptance-calibration.md', report.read_text(encoding='utf-8'), extra_names)
    controls = register['controls']
    ids = [control['id'] for control in controls]
    require(len(ids) == len(set(ids)), 'Duplicate acceptance control ID')
    controls_by_id = {control['id']: control for control in controls}
    workflow = context.load_yaml('.github/workflows/ci.yml')
    check_acceptance_workflow(_workflow_settings(workflow), controls_by_id['AC-07'])
    check_ci_calibration(controls_by_id['AC-07'], records)
    _check_acceptance_measurements(controls_by_id, records, measurements)
    _check_registered_controls(controls, records, measurements)
    context.record('acceptance-controls', 'Typed protocols are complete; measurement records bind known controls, '
                                          'registered dates and the hosted image; calibration evidence is '
                                          'excluded from acceptance verdicts.', len(ids))


def _load_calibration_records(
    context: ValidationContext, record_schema: Draft202012Validator, extra_names: Iterable[str],
) -> dict[str, dict]:
    """Load calibration evidence; for example, reject acceptance evidence in this directory."""
    records: dict[str, dict] = {}
    for path in sorted((context.root / 'spec/calibration').glob('*.json')):
        relative = path.relative_to(context.root).as_posix()
        text = path.read_text(encoding='utf-8')
        records[relative] = _load_identity_checked_json(relative, text, extra_names)
        record_schema.validate(records[relative])
        check_calibration_record(relative, records[relative])
    return records


def _load_acceptance_measurements(
    context: ValidationContext, record_schema: Draft202012Validator, extra_names: Iterable[str],
) -> list[dict]:
    """Load accepted measurements; for example, reject calibration-purpose entries."""
    measurements_directory = context.root / 'spec/measurements'
    if not measurements_directory.exists():
        return []
    measurements: list[dict] = []
    for path in sorted(measurements_directory.glob('*.json')):
        relative = path.relative_to(context.root).as_posix()
        text = path.read_text(encoding='utf-8')
        measurement = _load_identity_checked_json(relative, text, extra_names)
        record_schema.validate(measurement)
        require(measurement['purpose'] == 'acceptance',
                f"{relative} must be an acceptance record; calibration evidence belongs in spec/calibration")
        measurements.append(measurement)
    return measurements


def _check_acceptance_measurements(
    controls: Mapping[str, Mapping[str, object]], records: Mapping[str, dict], measurements: list[dict],
) -> None:
    """Check record bindings and unique IDs; for example, reject an unknown control."""
    for record in (*records.values(), *measurements):
        check_control_bindings(controls, record)
    measurement_ids = [record['id'] for record in measurements]
    require(len(measurement_ids) == len(set(measurement_ids)), 'Duplicate acceptance measurement ID')


def _check_registered_controls(
    controls: list[dict], records: Mapping[str, dict], measurements: list[dict],
) -> None:
    """Check every frozen control; for example, reject calibration used as acceptance evidence."""
    for control in controls:
        check_completeness(control)
        check_calibration_reference(control, records)
        require(verdict(control, records.values()) == 'not-run',
                f"{control['id']} has acceptance evidence in the calibration directory")
        verdict(control, measurements)
