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

from jsonschema import Draft202012Validator

from .context import ValidationContext, require

FROZEN_FIELDS = (
    'workload', 'control', 'sizes', 'seeds', 'timed_region', 'metric', 'unit', 'estimand', 'statistic',
    'decision_rule', 'warmup', 'interleaving', 'samples', 'outlier_policy', 'environment', 'cache_policy',
    'proof_scope', 'measurement_tool', 'analysis_script', 'calibration', 'registered_on', 'authority',
)
OUTCOME_VERDICTS = {
    'pass': 'pass', 'fail': 'fail', 'budget-exceeded': 'fail', 'resource-exhausted': 'fail',
    'inconclusive': 'inconclusive', 'missing': 'fail',
}
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


def check_amendment_chain(control: Mapping[str, object], sponsor: str) -> None:
    """Require registration, amendments, and the current digest to form one approved chain."""
    previous = control['registered_digest']
    for amendment in control['amendments']:
        require(amendment['replaces'] == previous, f"{control['id']} amendment does not replace digest {previous}")
        require(amendment['approved_by'] == sponsor, f"{control['id']} amendment is not approved by the sponsor")
        previous = amendment['new_digest']
    require(control['digest'] == previous, f"{control['id']} digest is not the end of its amendment chain")
    require(control['digest'] == frozen_digest(control), f"{control['id']} digest does not match its frozen fields")


def verdict(control: Mapping[str, object], records: Iterable[Mapping[str, object]]) -> str:
    """Decide an acceptance verdict; every retry counts and calibration never counts.

    Only acceptance records bound to the control's current digest are read. Any
    failing outcome fails; otherwise any inconclusive outcome is inconclusive;
    otherwise at least one record must pass. With no record the control is
    `not-run`.
    """
    outcomes = [OUTCOME_VERDICTS[record['outcome']] for record in records
                if record['purpose'] == 'acceptance' and record['control_id'] == control['id']
                and record['control_digest'] == control['digest']]
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
    Draft202012Validator(context.load('spec/acceptance-controls.schema.json')).validate(register)
    record_schema = Draft202012Validator(context.load('spec/measurement-record.schema.json'),
                                         format_checker=Draft202012Validator.FORMAT_CHECKER)
    records: dict[str, dict] = {}
    for path in sorted((context.root / 'spec/calibration').glob('*.json')):
        relative = path.relative_to(context.root).as_posix()
        text = path.read_text(encoding='utf-8')
        check_host_identity(relative, text, extra_names)
        records[relative] = json.loads(text)
        record_schema.validate(records[relative])
    report = context.root / 'docs/acceptance-calibration.md'
    check_host_identity('docs/acceptance-calibration.md', report.read_text(encoding='utf-8'), extra_names)
    sponsor = context.load('spec/decisions.json')['authorities']['roles']['sponsor']
    ids = [control['id'] for control in register['controls']]
    require(len(ids) == len(set(ids)), 'Duplicate acceptance control ID')
    for control in register['controls']:
        check_completeness(control)
        check_amendment_chain(control, sponsor)
        check_calibration_reference(control, records)
        require(verdict(control, records.values()) == 'not-run',
                f"{control['id']} has acceptance evidence in the calibration directory")
    context.record('acceptance-controls', 'Controls carry every frozen field, digests close their amendment chains, '
                                          'calibration records are cited and host-free, and no calibration record '
                                          'counts as acceptance evidence.', len(ids))
