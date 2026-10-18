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
import re
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .ci_controls import OUTCOME_VERDICTS, check_acceptance_workflow, check_ci_calibration, check_ci_measurement
from .context import ValidationContext, require

FROZEN_FIELDS = (
    'workload', 'control', 'sizes', 'seeds', 'timed_region', 'metric', 'unit', 'estimand', 'statistic',
    'decision_rule', 'warmup', 'interleaving', 'samples', 'outlier_policy', 'environment', 'cache_policy',
    'proof_scope', 'measurement_tool', 'analysis_script', 'calibration', 'registered_on', 'authority',
)
HOST_PATTERNS = (re.compile(r'/home/'), re.compile(r'/Users/'))


def frozen_digest(control: Mapping[str, object]) -> str:
    """Digest a control's frozen fields as canonical JSON; e.g. any threshold change changes it."""
    frozen = control['frozen']
    canonical = json.dumps({name: frozen[name] for name in FROZEN_FIELDS}, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def check_completeness(control: Mapping[str, object]) -> None:
    """Require exactly the frozen fields; a missing calibration reference fails by name."""
    present = set(control['frozen'])
    missing = sorted(set(FROZEN_FIELDS) - present)
    extra = sorted(present - set(FROZEN_FIELDS))
    require(not missing, f"{control['id']} lacks frozen fields: {', '.join(missing)}")
    require(not extra, f"{control['id']} has unregistered frozen fields: {', '.join(extra)}")


def check_outcome_verdicts(register: Mapping[str, object]) -> None:
    """Keep the declared outcome map identical to executable verdict semantics."""
    require(register.get('outcome_verdicts') == OUTCOME_VERDICTS,
            'Registered outcome_verdicts must match the executable outcome mapping')


def check_frozen_fields(register: Mapping[str, object]) -> None:
    """Keep the declared frozen-field list identical to the digest implementation."""
    require(register.get('frozen_fields') == list(FROZEN_FIELDS),
            'Registered frozen_fields must match the executable digest fields')


def check_amendment_chain(
    control: Mapping[str, object], sponsor: str, acceptance_records: Iterable[Mapping[str, object]] = (),
) -> None:
    """Validate sponsor approvals, amendment dates, and the registered digest chain."""
    require(control['digest'] == frozen_digest(control),
            f"{control['id']} digest does not match its frozen fields")
    previous = control['registered_digest']
    previous_date = date.fromisoformat(control['frozen']['registered_on'])
    measurements = [
        date.fromisoformat(record['recorded_on']) for record in acceptance_records
        if record['purpose'] == 'acceptance' and control['id'] in record['control_ids']
    ]
    earliest_measurement = min(measurements, default=None)
    seen_digests = {previous}
    for amendment in control['amendments']:
        amendment_date = date.fromisoformat(amendment['date'])
        require(amendment_date >= previous_date,
                f"{control['id']} amendment date cannot predate its previous effective date "
                f"{previous_date.isoformat()}")
        if earliest_measurement is not None:
            require(amendment_date < earliest_measurement,
                    f"{control['id']} amendment must predate the earliest acceptance measurement "
                    f"{earliest_measurement.isoformat()}; later changes require a new control identifier")
        require(amendment['replaces'] == previous, f"{control['id']} amendment does not replace digest {previous}")
        require(amendment['approved_by'] == sponsor, f"{control['id']} amendment is not approved by the sponsor")
        require(amendment['new_digest'] not in seen_digests,
                f"{control['id']} amendment repeats a digest in its chain")
        previous = amendment['new_digest']
        previous_date = amendment_date
        seen_digests.add(previous)
    require(control['digest'] == previous, f"{control['id']} digest is not the end of its amendment chain")


def check_sources(control: Mapping[str, object], root: Path) -> None:
    """Require each registered workload source to match its recorded SHA-256; an edit needs an amendment."""
    for source in control['frozen']['workload']['sources']:
        path = root / source['path']
        require(path.is_file(), f"{control['id']} source {source['path']} is missing")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        require(digest == source['sha256'],
                f"{control['id']} source {source['path']} changed since registration; amend the control")


def digest_dates(control: Mapping[str, object]) -> list[tuple[str, str]]:
    """Pair every registered digest with its effective date; e.g. amendments add later bindings."""
    bindings = [(control['registered_digest'], control['frozen']['registered_on'])]
    bindings.extend((amendment['new_digest'], amendment['date']) for amendment in control['amendments'])
    return bindings


def check_measurement_binding(control: Mapping[str, object], record: Mapping[str, object]) -> bool:
    """Validate a record's control history and say whether it binds the current digest."""
    require(record['purpose'] == 'acceptance' and control['id'] in record['control_ids'],
            f"{record['id']} is not acceptance evidence for {control['id']}")
    bindings = digest_dates(control)
    record_digest = record['control_digest']
    digest_positions = [index for index, (digest, _) in enumerate(bindings) if digest == record_digest]
    require(bool(digest_positions),
            f"{record['id']} cites unknown digest {record_digest} for {control['id']}")
    index = digest_positions[-1]
    effective_date = bindings[index][1]
    recorded_on = record['recorded_on']
    require(recorded_on >= effective_date,
            f"{record['id']} predates registration of {control['id']} digest {record_digest}")
    require(record['runner_image'] == control['frozen']['environment']['image'],
            f"{record['id']} does not use {control['id']}'s registered runner image")
    require(record['hardware']['class'] == 'github-hosted-runner'
            and record['hardware']['os_family'] == 'Ubuntu 24.04',
            f"{record['id']} was not measured on the registered GitHub-hosted Ubuntu 24.04 runner")
    return record_digest == control['digest']


def check_calibration_record(name: str, record: Mapping[str, object]) -> None:
    """Keep acceptance evidence out of the calibration-only directory."""
    require(record['purpose'] == 'calibration',
            f"{name} must be a calibration record; acceptance evidence belongs in spec/measurements")


def check_control_bindings(controls: Mapping[str, Mapping[str, object]], record: Mapping[str, object]) -> None:
    """Reject measurement references to controls that are absent from the register."""
    for control_id in record['control_ids']:
        require(control_id in controls, f"{record['id']} cites unknown control {control_id}")


def verdict(control: Mapping[str, object], records: Iterable[Mapping[str, object]]) -> str:
    """Decide an acceptance verdict; every retry counts and calibration never counts.

    Valid historical digests are checked but do not affect the current verdict.
    Any failing outcome fails; otherwise any inconclusive outcome is
    inconclusive; otherwise at least one current record must pass. With no
    current record the control is `not-run`.
    """
    matching_records = [record for record in records
                        if record['purpose'] == 'acceptance' and control['id'] in record['control_ids']]
    outcomes = []
    for record in matching_records:
        is_current = check_measurement_binding(control, record)
        check_ci_measurement(control, record)
        if is_current:
            outcomes.append(OUTCOME_VERDICTS[record['outcome']])
    if not outcomes:
        return 'not-run'
    if 'fail' in outcomes:
        return 'fail'
    return 'inconclusive' if 'inconclusive' in outcomes else 'pass'


def check_host_identity(name: str, text: str, extra_names: Iterable[str] = ()) -> None:
    """Reject home paths, which carry user names, and any supplied host name in a committed record (D11)."""
    for pattern in HOST_PATTERNS:
        require(pattern.search(text) is None, f'{name} contains a home path')
    for value in extra_names:
        require(not value or value not in text, f'{name} contains host identity {value!r}')


def check_calibration_reference(control: Mapping[str, object], records: Mapping[str, dict]) -> None:
    """Require a calibrated control to cite an existing calibration record for itself."""
    calibration = control['frozen']['calibration']
    if calibration['status'] == 'not-calibrated':
        require(bool(calibration.get('reason')), f"{control['id']} must say why it is not calibrated")
        return
    record = records.get(calibration['record'])
    require(record is not None, f"{control['id']} cites missing calibration record {calibration['record']}")
    require(record['purpose'] == 'calibration' and control['id'] in record['control_ids'],
            f"{calibration['record']} is not a calibration record for {control['id']}")


def check_acceptance_controls(context: ValidationContext, extra_names: Iterable[str] = ()) -> None:
    """Validate the control register, its calibration records, and the calibration report."""
    register = context.load('spec/acceptance-controls.json')
    Draft202012Validator(
        context.load('spec/acceptance-controls.schema.json'),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    ).validate(register)
    check_outcome_verdicts(register)
    check_frozen_fields(register)
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
    workflow_path = context.root / '.github/workflows/ci.yml'
    check_acceptance_workflow(yaml.safe_load(workflow_path.read_text()), controls_by_id['AC-07'])
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
    sponsor = context.load('spec/decisions.json')['authorities']['roles']['sponsor']
    for control in controls:
        check_completeness(control)
        check_amendment_chain(control, sponsor, measurements)
        check_sources(control, context.root)
        check_calibration_reference(control, records)
        require(verdict(control, records.values()) == 'not-run',
                f"{control['id']} has acceptance evidence in the calibration directory")
        verdict(control, measurements)
