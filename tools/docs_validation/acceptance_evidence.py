"""Validate measurement bindings and acceptance evidence independently of I/O.

The documentation checker composition supplies parsed records. These rules are
owned by that checker and its focused tests; they are not general-purpose
measurement or hardware-identity APIs.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .acceptance_registration import digest_dates
from .ci_controls import OUTCOME_VERDICTS, check_ci_measurement
from .context import require

HOST_PATTERNS = (re.compile(r'/home/'), re.compile(r'/Users/'))

def check_measurement_binding(control: Mapping[str, object], record: Mapping[str, object]) -> bool:
    """Validate a measurement's history and report whether it uses the current digest.

    Parameters
    ----------
    control : Mapping[str, object]
        Registered control whose digest history governs the measurement.
    record : Mapping[str, object]
        Acceptance record naming the control, digest, date, runner, and hardware class.

    Returns
    -------
    bool
        True for the current digest and False for a valid historical digest.

    Raises
    ------
    AssertionError
        If the record is unbound, predates registration, or uses another environment.
    KeyError
        If the control or record omits a field required for binding.

    Examples
    --------
    check_measurement_binding(control, record) returns True for a current result.
    """
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
    """Require a record loaded from calibration storage to declare calibration purpose.

    Parameters
    ----------
    name : str
        Repository-relative path used in any diagnostic.
    record : Mapping[str, object]
        Parsed measurement record.

    Returns
    -------
    None
        Returns only for a calibration-purpose record.

    Raises
    ------
    AssertionError
        If the record claims acceptance purpose.
    KeyError
        If the record omits its purpose field.

    Examples
    --------
    check_calibration_record(path, record) accepts calibration evidence.
    """
    require(record['purpose'] == 'calibration',
            f"{name} must be a calibration record; acceptance evidence belongs in spec/measurements")

def check_control_bindings(controls: Mapping[str, Mapping[str, object]], record: Mapping[str, object]) -> None:
    """Require every control named by a measurement to exist in the register.

    Parameters
    ----------
    controls : Mapping[str, Mapping[str, object]]
        Registered controls indexed by identifier.
    record : Mapping[str, object]
        Measurement record containing control_ids.

    Returns
    -------
    None
        Returns only when every named control is registered.

    Raises
    ------
    AssertionError
        If the record references an unknown control identifier.
    KeyError
        If the record omits its identifier or control list.

    Examples
    --------
    check_control_bindings(controls, record) accepts known control IDs.
    """
    for control_id in record['control_ids']:
        require(control_id in controls, f"{record['id']} cites unknown control {control_id}")

def verdict(control: Mapping[str, object], records: Iterable[Mapping[str, object]]) -> str:
    """Return the acceptance verdict after binding every matching measurement.

    Valid historical digests are checked but do not affect the current verdict.
    Any failing outcome fails; otherwise any inconclusive outcome is
    inconclusive; otherwise at least one current record must pass. With no
    current record the control is not-run.

    Parameters
    ----------
    control : Mapping[str, object]
        Registered control being assessed.
    records : Iterable[Mapping[str, object]]
        Calibration or acceptance records available to the assessment.

    Returns
    -------
    str
        One of pass, fail, inconclusive, or not-run.

    Raises
    ------
    AssertionError
        If a matching acceptance record violates digest, environment, or AC-07 rules.
    KeyError
        If a matching record omits a required field.
    ValueError
        If an AC-07 attempt timestamp is malformed.

    Examples
    --------
    verdict(control, []) returns not-run without acceptance evidence.
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
    """Reject home paths and supplied host names from committed evidence.

    Parameters
    ----------
    name : str
        Record or document name used in any diagnostic.
    text : str
        Serialized content to scan.
    extra_names : Iterable[str], optional
        Host names supplied by the test or caller.

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

def check_calibration_reference(control: Mapping[str, object], records: Mapping[str, dict]) -> None:
    """Require a calibrated control to cite an existing record for itself.

    Parameters
    ----------
    control : Mapping[str, object]
        Control whose calibration declaration is checked.
    records : Mapping[str, dict]
        Calibration records indexed by repository-relative path.

    Returns
    -------
    None
        Returns for a valid calibration record or a reasoned not-calibrated entry.

    Raises
    ------
    AssertionError
        If the calibration record is absent, misbound, or a missing status reason is given.
    KeyError
        If the control omits its calibration declaration or required field.

    Examples
    --------
    check_calibration_reference(control, records) accepts a valid cited record.
    """
    calibration = control['frozen']['calibration']
    if calibration['status'] == 'not-calibrated':
        require(bool(calibration.get('reason')), f"{control['id']} must say why it is not calibrated")
        return
    record = records.get(calibration['record'])
    require(record is not None, f"{control['id']} cites missing calibration record {calibration['record']}")
    require(record['purpose'] == 'calibration' and control['id'] in record['control_ids'],
            f"{calibration['record']} is not a calibration record for {control['id']}")
