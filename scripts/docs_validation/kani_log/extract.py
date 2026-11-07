"""Extract per-harness facts from a Kani log, or refuse the log (VO-11a).

The evidence gate must not believe a record that says a proof ran; it must read
the proof's own output. This module is the half of that which looks at the
log: it turns the text into the facts a decision can be taken from, and it
refuses anything it does not fully recognise. The grammar it recognises is
declared in :mod:`docs_validation.kani_log.syntax`.

Unknown chatter *between* reports is accepted, so a Kani release that adds a
post-processing message does not break the parser. Refusal is for structure the
parser cannot account for inside a report: a missing banner or ``Manual Harness
Summary``, a truncated or duplicated harness block, a block that ends without
its verdict, summary counts that disagree with the checks listed, or an
unrecognised line inside a report block. Those are the ways a log can be
subtly wrong while looking successful, which is the class the gate exists to
reject (``tool-error`` in VO-11b).

The parsed value is deliberately dull — statuses, identifiers, locations, and
counts — so :mod:`docs_validation.kani_log.decide` can map it to admission
facts without I/O.
"""
from __future__ import annotations

from collections.abc import Iterable

from .model import HarnessBlock, KaniLog, ManualSummary
from .reader import Reader
from .syntax import (
    BANNER, HARNESS_START, LIST_WRITTEN, NO_UNWINDING_ASSERTIONS_FLAG,
    SUPPORTED_VERSIONS, UNSUPPORTED_PRELUDE, UNWINDING_BOUND_FLAGS,
    VERIFICATION_TIME, KaniLogError, PropertyResult,
)

__all__ = [
    'HarnessBlock', 'KaniLog', 'KaniLogError', 'ManualSummary', 'PropertyResult',
    'parse', 'unwinding_checks_enabled',
]


def parse(text: str) -> KaniLog:
    """Read one Kani log into per-harness facts, or refuse it.

    Parameters
    ----------
    text
        The complete captured output of one Kani invocation, with stdout and
        stderr in that order.

    Returns
    -------
    KaniLog
        The banner, the output format, every harness block, the manual summary,
        and the constructs Kani named as unsupported.

    Raises
    ------
    KaniLogError
        If the log is truncated, duplicated, interleaved, count-inconsistent,
        or otherwise not a complete Kani report.

    Examples
    --------
    ``parse("not a log")`` raises ``KaniLogError('structural error: the log
    does not begin with a Kani banner')``, because a log without a banner
    cannot be attributed to a Kani release.
    """
    reader = Reader(text.splitlines())
    banner = reader.banner()
    if banner is None:
        raise KaniLogError('the log does not begin with a Kani banner')
    if banner[0] not in SUPPORTED_VERSIONS:
        raise KaniLogError(
            f'the log is from Kani {banner[0]}, but this parser reads {sorted(SUPPORTED_VERSIONS)}')
    blocks: list[HarnessBlock] = []
    manual: ManualSummary | None = None
    unsupported: list[str] = []
    is_list = False
    while not reader.exhausted:
        line = reader.peek()
        if line == 'Manual Harness Summary:':
            if manual is not None:
                raise KaniLogError(f'{reader.where()}: a second manual harness summary')
            manual = reader.manual()
        elif line == UNSUPPORTED_PRELUDE:
            unsupported.extend(reader.unsupported_constructs())
        elif line.startswith(LIST_WRITTEN):
            is_list = True
            reader.take()
        elif header := HARNESS_START.match(line):
            blocks.append(reader.block(header))
        else:
            reader.take()
    return _reconcile(banner[0], blocks, manual, is_list, tuple(unsupported))


def _reconcile(version: str, blocks: Iterable[HarnessBlock], manual: ManualSummary | None,
               is_list: bool, unsupported: tuple[str, ...]) -> KaniLog:
    """Reconcile the log's parts, refusing any combination that cannot be real."""
    returned = tuple(blocks)
    if is_list:
        if returned:
            raise KaniLogError('the log claims to be both an inventory and a verification run')
        return KaniLog(version, 'inventory', (), None, unsupported)
    if not returned:
        raise KaniLogError('the log reports no harness results')
    if manual is None:
        raise KaniLogError('the log is truncated: it has no manual harness summary')
    names = tuple(block.name for block in returned)
    if len(set(names)) != len(names):
        raise KaniLogError('a harness was reported twice in the same run')
    succeeded = tuple(block.name for block in returned if block.succeeded)
    failed = tuple(block.name for block in returned if block.verdict == 'FAILED')
    if (len(succeeded), len(failed), len(returned)) != (manual.verified, manual.failures, manual.total):
        raise KaniLogError(
            f'the manual summary claims {manual.verified} verified and {manual.failures} failed of '
            f'{manual.total}, but the blocks report {len(succeeded)} verified and {len(failed)} failed '
            f'of {len(returned)}')
    if manual.failed != failed:
        raise KaniLogError(
            f'the manual summary names failures {list(manual.failed)}, but the blocks report {list(failed)}')
    return KaniLog(version, 'regular', returned, manual, unsupported)


def unwinding_checks_enabled(block: HarnessBlock) -> bool | None:
    """Report whether the solver was asked to generate unwinding assertions.

    ``True`` when the echoed CBMC command carries an unwinding bound
    (``--unwind`` or ``--unwindset``) and not ``--no-unwinding-assertions``;
    ``False`` when it carries no bound or disables the assertions; ``None`` when
    the block echoed no solver command, so nothing can be concluded.

    The rule is CBMC's, not a guess: a bound is what makes CBMC emit the
    assertion in the first place, which is why Kani's driver never passes
    ``--unwinding-assertions`` and instead disables them with
    ``--no-unwinding-assertions``. ``None`` and ``False`` both make VO-11b
    report the run as ``focused``, because neither can confirm that an
    unwinding failure would have been observed.

    Examples
    --------
    The corpus's ``insufficient_unwind`` log echoes ``--unwind 2`` and so
    returns True; the ``verified`` log echoes a ``cbmc`` command without a
    bound and returns False.
    """
    if block.solver_command is None:
        return None
    if NO_UNWINDING_ASSERTIONS_FLAG in block.solver_command:
        return False
    return any(flag in block.solver_command for flag in UNWINDING_BOUND_FLAGS)
