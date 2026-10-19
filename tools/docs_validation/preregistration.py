"""Validate pre-registered acceptance controls and their measurement records (ADR-0008).

A control freezes everything that decides its result before any acceptance
measurement exists. Its digest is SHA-256 over the canonical JSON of the frozen
fields; a later change must arrive as a sponsor-approved amendment whose
`replaces` equals the previous digest (VO-11). Outcomes map so that budget
overruns, exhausted resources, and missing records never pass, and calibration
records never count as acceptance evidence (VO-12). Records describe hardware by
class only, never by host name or home path (VO-16).
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping

from jsonschema import Draft202012Validator

from .acceptance_evidence import (
    check_calibration_record, check_calibration_reference, check_control_bindings, check_host_identity,
    check_measurement_binding, verdict,
)
from .acceptance_registration import (
    FROZEN_FIELDS, check_amendment_chain, check_completeness, check_registration_declarations, check_sources,
    digest_dates, frozen_digest,
)
from .ci_controls import (
    OUTCOME_VERDICTS, AcceptanceWorkflowSettings, check_acceptance_workflow, check_ci_calibration,
    check_ci_measurement,
)
from .context import ValidationContext, require

__all__ = [
    'AcceptanceWorkflowSettings', 'FROZEN_FIELDS', 'OUTCOME_VERDICTS', 'check_acceptance_controls',
    'check_acceptance_workflow', 'check_amendment_chain', 'check_calibration_record',
    'check_calibration_reference', 'check_ci_calibration', 'check_ci_measurement', 'check_completeness',
    'check_control_bindings', 'check_host_identity', 'check_measurement_binding', 'check_registration_declarations',
    'check_sources', 'digest_dates', 'frozen_digest', 'verdict',
]















def _workflow_settings(workflow: object) -> AcceptanceWorkflowSettings:
    """Adapt parsed CI YAML into AC-07 values; e.g. extract image and job timeout."""
    jobs = workflow.get('jobs', {}) if isinstance(workflow, Mapping) else {}
    job = jobs.get('build-test') if isinstance(jobs, Mapping) else None
    return AcceptanceWorkflowSettings(
        runner_image=job.get('runs-on') if isinstance(job, Mapping) else None,
        timeout_minutes=job.get('timeout-minutes') if isinstance(job, Mapping) else None,
    )


def _load_source_digests(context: ValidationContext, controls: list[dict]) -> dict[str, str]:
    """Hash registered workload sources in the composition path; e.g. bind CI YAML to AC-07."""
    paths = sorted({source['path'] for control in controls for source in control['frozen']['workload']['sources']})
    digests: dict[str, str] = {}
    for path in paths:
        try:
            digests[path] = hashlib.sha256(context.read_bytes(path)).hexdigest()
        except OSError as error:
            raise ValueError(f'Unable to read registered workload source {path}: {error}') from error
    return digests
















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
        If a register, source binding, calibration record, or measurement violates a rule.
    jsonschema.ValidationError
        If a control or measurement does not match its schema.
    ValueError
        If the workflow YAML is malformed or a registered workload source cannot
        be read.
    OSError
        If a register, schema, calibration record, measurement record, or
        calibration report cannot be read.

    Examples
    --------
    check_acceptance_controls(context) records a passing check for a valid register.
    """
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
    _check_registered_controls(controls, context, records, measurements)
    context.record('acceptance-controls', 'Typed frozen protocols close their approved digest chains; measurement '
                                          'records bind known controls, registered dates and the hosted image; '
                                          'calibration evidence is excluded from acceptance verdicts.', len(ids))


def _load_calibration_records(
    context: ValidationContext, record_schema: Draft202012Validator, extra_names: Iterable[str],
) -> dict[str, dict]:
    """Load calibration evidence; for example, reject acceptance evidence in this directory."""
    records: dict[str, dict] = {}
    for path in sorted((context.root / 'spec/calibration').glob('*.json')):
        relative = path.relative_to(context.root).as_posix()
        text = path.read_text(encoding='utf-8')
        check_host_identity(relative, text, extra_names)
        records[relative] = json.loads(text)
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
        check_host_identity(relative, text, extra_names)
        measurement = json.loads(text)
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
    controls: list[dict], context: ValidationContext, records: Mapping[str, dict], measurements: list[dict],
) -> None:
    """Check every frozen control; for example, reject calibration used as acceptance evidence."""
    source_digests = _load_source_digests(context, controls)
    sponsor = context.load('spec/decisions.json')['authorities']['roles']['sponsor']
    for control in controls:
        check_completeness(control)
        check_amendment_chain(control, sponsor, measurements)
        check_sources(control, source_digests)
        check_calibration_reference(control, records)
        require(verdict(control, records.values()) == 'not-run',
                f"{control['id']} has acceptance evidence in the calibration directory")
        verdict(control, measurements)
