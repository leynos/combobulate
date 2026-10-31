"""Validate registered acceptance protocols independently of repository I/O.

The documentation checker composition supplies parsed values. These rules are
owned by that checker and its focused tests; they are not general-purpose JSON
or repository APIs.
"""
from __future__ import annotations

from collections.abc import Mapping

from .ci_controls import OUTCOME_VERDICTS
from .context import require

FROZEN_FIELDS = (
    'workload', 'control', 'sizes', 'seeds', 'timed_region', 'metric', 'unit', 'estimand', 'statistic',
    'decision_rule', 'warmup', 'interleaving', 'samples', 'outlier_policy', 'environment', 'cache_policy',
    'proof_scope', 'measurement_tool', 'analysis_script', 'calibration', 'registered_on',
)

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
         'Registered frozen_fields must match the executable frozen-field list'),
    )
    for name, expected, message in declarations:
        require(register.get(name) == expected, message)
