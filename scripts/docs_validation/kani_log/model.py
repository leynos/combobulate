"""Hold the parsed value types a Kani log produces.

:mod:`~docs_validation.kani_log.extract` walks the text and builds these; the
decision function and the tests read them. They live apart from the walk for two
reasons: the walker is the only thing that needs the grammar, and a value type
that names no regular expression is easier to construct in a test than one that
shares a module with a line cursor.

:class:`HarnessBlock` is deliberately mutable. It is filled field by field as
one block is read, and the counts are only reconcilable once the whole block has
been seen; the frozen types beside it are the finished facts.

Examples
--------
>>> HarnessBlock(name='h::x', verdict='SUCCESSFUL').succeeded
True
>>> KaniLog('1.0.0', 'regular', (), None, ()).harnesses
()
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .syntax import FailedCheck, PropertyResult

__all__ = ['HarnessBlock', 'KaniLog', 'ManualSummary']


@dataclass(slots=True)
class HarnessBlock:
    """Everything one ``Checking harness`` block reported, before ownership is resolved."""

    name: str
    properties: list[PropertyResult] = field(default_factory=list)
    failures: list[FailedCheck] = field(default_factory=list)
    failed_count: int | None = None
    total_count: int | None = None
    other_count: int = 0
    other_kind: str | None = None
    covered_satisfied: int | None = None
    covered_total: int | None = None
    covered_unreachable: int | None = None
    verdict: str | None = None
    panics_as_expected: bool = False
    solver_command: str | None = None
    seen_verification_time: bool = False
    timed_out: bool = False
    unwinding_reported: bool = False
    has_results: bool = False

    @property
    def succeeded(self) -> bool:
        """Report whether Kani declared this block successful.

        ``SUCCESSFUL (encountered one or more panics as expected)`` is still a
        success for the harness, which is what a ``#[kani::should_panic]``
        claim relies on, so the note does not change the verdict.
        """
        return self.verdict == 'SUCCESSFUL'

    @property
    def checks(self) -> tuple[PropertyResult, ...]:
        """Return the assertion and unwinding checks, excluding covers."""
        return tuple(item for item in self.properties if not item.is_cover)

    @property
    def covers(self) -> tuple[PropertyResult, ...]:
        """Return the declared success witnesses."""
        return tuple(item for item in self.properties if item.is_cover)

    def owned(self, harness: str) -> tuple[PropertyResult, ...]:
        """Return the checks whose identifier belongs to ``harness``."""
        return tuple(item for item in self.properties if item.owner == harness)


@dataclass(frozen=True, slots=True)
class ManualSummary:
    """The counts Kani prints once after every harness block."""

    verified: int
    failures: int
    total: int
    failed: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KaniLog:
    """The facts one log states, without interpretation.

    ``format`` is ``regular`` for a verification run and ``inventory`` for
    ``kani list`` output, which carries no harness verdicts. A log that is
    neither cannot be decided from, and :func:`~docs_validation.kani_log.parse`
    refuses it.

    The banner's *kind* (``cargo plugin``) is deliberately not kept. Nothing
    reads it: the version is what selects the grammar, and a driver shape that
    changes would change the report, which the parser already refuses.
    """

    banner_version: str
    format: str
    blocks: tuple[HarnessBlock, ...]
    manual: ManualSummary | None
    unsupported_constructs: tuple[str, ...]

    @property
    def harnesses(self) -> tuple[str, ...]:
        """Name every harness that produced a verification block, in log order."""
        return tuple(block.name for block in self.blocks)
