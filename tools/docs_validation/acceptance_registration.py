"""Validate registered acceptance protocols independently of repository I/O.

The documentation checker composition supplies parsed values. These rules are
owned by that checker and its focused tests; they are not general-purpose JSON
or repository APIs.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import date

from .ci_controls import OUTCOME_VERDICTS
from .context import require

FROZEN_FIELDS = (
    'workload', 'control', 'sizes', 'seeds', 'timed_region', 'metric', 'unit', 'estimand', 'statistic',
    'decision_rule', 'warmup', 'interleaving', 'samples', 'outlier_policy', 'environment', 'cache_policy',
    'proof_scope', 'measurement_tool', 'analysis_script', 'calibration', 'registered_on', 'authority',
)

def frozen_digest(control: Mapping[str, object]) -> str:
    """Return the SHA-256 digest of a control's canonical frozen fields.

    Parameters
    ----------
    control : Mapping[str, object]
        Registered control containing every frozen field.

    Returns
    -------
    str
        Lowercase hexadecimal SHA-256 digest.

    Raises
    ------
    KeyError
        If the control omits its frozen object or a registered field.
    TypeError
        If a frozen value cannot be serialized as JSON.

    Examples
    --------
    frozen_digest(control) returns the value to store in control['digest'].
    """
    frozen = control['frozen']
    canonical = json.dumps({name: frozen[name] for name in FROZEN_FIELDS}, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def check_completeness(control: Mapping[str, object]) -> None:
    """Require a control to contain exactly the registered frozen fields.

    Parameters
    ----------
    control : Mapping[str, object]
        Control whose frozen object is checked.

    Returns
    -------
    None
        Returns only when no frozen field is missing or unregistered.

    Raises
    ------
    AssertionError
        If the frozen object omits a required field or contains an extra field.
    KeyError
        If the control omits its frozen object or identifier.

    Examples
    --------
    check_completeness(control) accepts a control with all registered fields.
    """
    present = set(control['frozen'])
    missing = sorted(set(FROZEN_FIELDS) - present)
    extra = sorted(present - set(FROZEN_FIELDS))
    require(not missing, f"{control['id']} lacks frozen fields: {', '.join(missing)}")
    require(not extra, f"{control['id']} has unregistered frozen fields: {', '.join(extra)}")

def check_registration_declarations(register: Mapping[str, object]) -> None:
    """Require top-level register declarations to match executable semantics.

    Parameters
    ----------
    register : Mapping[str, object]
        Parsed acceptance-control register.

    Returns
    -------
    None
        Returns only when its outcome map and frozen-field list are exact.

    Raises
    ------
    AssertionError
        If either declaration differs from its executable counterpart.

    Examples
    --------
    check_registration_declarations(register) accepts the canonical declarations.
    """
    declarations = (
        ('outcome_verdicts', OUTCOME_VERDICTS,
         'Registered outcome_verdicts must match the executable outcome mapping'),
        ('frozen_fields', list(FROZEN_FIELDS),
         'Registered frozen_fields must match the executable digest fields'),
    )
    for name, expected, message in declarations:
        require(register.get(name) == expected, message)

def check_amendment_chain(
    control: Mapping[str, object], sponsor: str, acceptance_records: Iterable[Mapping[str, object]] = (),
) -> None:
    """Validate sponsor approvals, dates, and the registered digest chain.

    Parameters
    ----------
    control : Mapping[str, object]
        Control with its initial digest and append-only amendments.
    sponsor : str
        Registered sponsor allowed to approve amendments.
    acceptance_records : Iterable[Mapping[str, object]], optional
        Records used to forbid amendments on or after the earliest measurement.

    Returns
    -------
    None
        Returns only when every amendment extends the approved digest chain.

    Raises
    ------
    AssertionError
        If an amendment changes authority, chronology, or digest ancestry.
    KeyError
        If a control, amendment, or measurement omits a required field.
    TypeError
        If a frozen field cannot be serialized as JSON.
    ValueError
        If a registration, amendment, or measurement date is not ISO formatted.

    Examples
    --------
    check_amendment_chain(control, sponsor) validates an unamended control.
    """
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

def check_sources(control: Mapping[str, object], source_digests: Mapping[str, str]) -> None:
    """Require workload sources and any analysis script to have registered digests.

    Parameters
    ----------
    control : Mapping[str, object]
        Control whose workload and analysis-script sources are registered.
    source_digests : Mapping[str, str]
        SHA-256 values keyed by registered source path.

    Returns
    -------
    None
        Returns only when every registered source digest matches and each named
        analysis script is among the hashed workload sources.

    Raises
    ------
    AssertionError
        If a source is missing or differs from its registered digest, or an
        analysis script has no matching hashed source.
    KeyError
        If a control or source omits a required path or digest field.

    Examples
    --------
    check_sources(control, digests) accepts matching source hashes and script bindings.
    """
    sources = control['frozen']['workload']['sources']
    for source in sources:
        digest = source_digests.get(source['path'])
        require(digest is not None, f"{control['id']} source {source['path']} is missing")
        require(digest == source['sha256'],
                f"{control['id']} source {source['path']} changed since registration; amend the control")
    analysis_script = control['frozen']['analysis_script']
    if isinstance(analysis_script, Mapping) and analysis_script['path'] is not None:
        script_path = analysis_script['path']
        require(any(source['path'] == script_path for source in sources),
                f"{control['id']} analysis script {script_path} has no matching hashed workload source")

def digest_dates(control: Mapping[str, object]) -> list[tuple[str, str]]:
    """Pair each registered digest with the date when it became effective.

    Parameters
    ----------
    control : Mapping[str, object]
        Control with its initial registration and amendments.

    Returns
    -------
    list[tuple[str, str]]
        Ordered (digest, effective_date) pairs from initial registration onward.

    Raises
    ------
    KeyError
        If registration or amendment digest fields are absent.

    Examples
    --------
    digest_dates(control) includes one pair for each approved amendment.
    """
    bindings = [(control['registered_digest'], control['frozen']['registered_on'])]
    bindings.extend((amendment['new_digest'], amendment['date']) for amendment in control['amendments'])
    return bindings
