"""Define the immutable evidence facts consumed only by roadmap closure.

The evidence-record adapter owns schema translation. MS-3 predicates consume
this value without knowing serialized record keys or performing I/O.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from .evidence_gate import Level


@dataclass(frozen=True)
class ClosureEvidence:
    """Carry one admission and its closure facts; no schema or filesystem state."""

    component_id: str
    recorded_on: datetime.date
    source_revision: str | None
    outcome: str
    binding_is_current: bool
    admission_level: Level
    admission_reasons: tuple[str, ...]
