"""Walk one Kani log line by line with the grammar from :mod:`~docs_validation.kani_log.syntax`.

This is the cursor half of the extractor: it consumes one report construct at a
time and raises :class:`~docs_validation.kani_log.syntax.KaniLogError` wherever
the next line is not one the grammar accounts for. Keeping it separate leaves
:mod:`~docs_validation.kani_log.extract` as the recogniser — banner, blocks,
manual summary — which is the part a new Kani release is compared against.

A line-at-a-time cursor is enough because every report construct is
line-delimited, and it keeps errors pointing at the line that broke the grammar
rather than at an offset in a string.
"""
from __future__ import annotations

import re

from .model import HarnessBlock, ManualSummary
from .syntax import (
    BANNER, CBMC_FAILED, CHECK, CHECK_FIELDS, CHECK_STATUSES, COVER, COMPLETE,
    FAILED_CHECK, FAILED_FOR, FAILED_LOCATION, FIELD, HARNESS_START, NOISE_PREFIXES,
    OTHER_STATUS, SOLVER_COMMAND, TIMED_OUT, TOTAL, UNSUPPORTED_ENTRY,
    UNSUPPORTED_REACHABLE, UNWINDING_FAILED, VERIFICATION, VERIFICATION_TIME,
    FailedCheck, KaniLogError, PropertyResult,
)

__all__ = ['Reader', 'is_noise']


class Reader:
    """Walk the log once, keeping the cursor position for error messages.

    A line-at-a-time cursor is enough because every report construct is
    line-delimited, and it keeps errors pointing at the line that broke the
    grammar rather than at an offset in a string.
    """

    def __init__(self, lines: list[str]) -> None:
        """Start at the first line of a log already split into lines."""
        self._lines = lines
        self._index = 0

    @property
    def exhausted(self) -> bool:
        """Report whether every line has been consumed."""
        return self._index >= len(self._lines)

    def where(self) -> str:
        """Describe the current position as a 1-based line number."""
        return f'line {self._index + 1}'

    def peek(self) -> str:
        """Return the current line without consuming it."""
        return self._lines[self._index]

    def take(self) -> str:
        """Consume and return the current line, or raise when past the end."""
        if self.exhausted:
            raise KaniLogError(f'{self.where()}: the log ends where more output was required')
        line = self._lines[self._index]
        self._index += 1
        return line

    def banner(self) -> tuple[str, str] | None:
        """Consume the version banner if the log opens with one."""
        if self.exhausted:
            return None
        match = BANNER.match(self._lines[0])
        if match is None:
            return None
        self.take()
        return match['version'], match['kind']

    def block(self, match: re.Match[str]) -> HarnessBlock:
        """Consume one ``Checking harness`` block through its verification time.

        The header match is supplied by the caller, which has already recognised
        the line: re-matching here would make the "expected a harness header"
        branch unreachable, and a branch no input can reach is not a refusal a
        log producer will ever read.
        """
        block = HarnessBlock(name=match['name'])
        self.take()
        while not self.exhausted:
            line = self.peek()
            verdict = VERIFICATION.match(line)
            if line == 'RESULTS:':
                self.take()
                self.results(block)
            elif line == 'SUMMARY:':
                self.take()
                self.summary(block)
            elif verdict is not None:
                self.verification(block, verdict)
            elif VERIFICATION_TIME.match(line):
                self.take()
                block.seen_verification_time = True
                self.require_complete(block)
                return block
            elif line == 'Manual Harness Summary:':
                self.require_complete(block)
                return block
            elif line == UNWINDING_FAILED:
                block.unwinding_reported = True
                self.take()
            elif line.startswith(TIMED_OUT):
                block.timed_out = True
                self.take()
            elif line.startswith(SOLVER_COMMAND):
                block.solver_command = line
                self.take()
            elif line in (CBMC_FAILED, UNSUPPORTED_REACHABLE) or is_noise(line):
                self.take()
            elif HARNESS_START.match(line) is not None:
                # A second harness began before this one reported. The outer
                # loop appends the new block, and reconciliation then finds this
                # one has no verdict or no summary.
                self.require_complete(block)
                return block
            elif block.verdict is None and not block.has_results and block.failed_count is None:
                # The solver's own transcript sits between the harness header
                # and the report. Its wording belongs to CBMC, not to Kani, so
                # it is skipped by position rather than by matching every line.
                self.take()
            else:
                raise KaniLogError(
                    f'{self.where()}: unrecognised line in the block for {block.name!r}: {line!r}')
        raise KaniLogError(f'the log is truncated inside the block for {block.name!r}')

    def require_complete(self, block: HarnessBlock) -> None:
        """Reconcile one block's counts against the checks it listed."""
        if block.verdict is None:
            raise KaniLogError(f'the block for {block.name!r} ends without a verification result')
        if block.timed_out and not block.has_results:
            # A timeout aborts CBMC before it reports any check, so the block has
            # no results, no summary, and no verification time. Its verdict alone
            # is the fact.
            return
        if not block.seen_verification_time:
            # `Verification Time` is the last line of every non-timeout block.
            # Requiring it is what makes truncating a complete log detectable at
            # all: everything after the summary is optional chatter, so without
            # this a log cut off just past its verdict would still parse.
            raise KaniLogError(
                f'the log is truncated: the block for {block.name!r} has no verification time')
        if block.failed_count is None or block.total_count is None:
            raise KaniLogError(f'the block for {block.name!r} has no summary')
        checks = block.checks
        if len(checks) != block.total_count:
            raise KaniLogError(
                f'the block for {block.name!r} counts {block.total_count} checks but lists {len(checks)}')
        failed = sum(1 for item in checks if item.status == 'FAILURE')
        if failed != block.failed_count:
            raise KaniLogError(
                f'the block for {block.name!r} counts {block.failed_count} failures but lists {failed}')
        # Every failed check is explained once, and the explanation carries the
        # source location Kani attributes it to. Requiring both makes deleting a
        # `Failed Checks:` line, or the ` File:` line beneath it, a structural
        # error: otherwise the count would still reconcile while the one fact a
        # record could not have invented — where the failure was — silently
        # vanished.
        if len(block.failures) != block.failed_count:
            raise KaniLogError(
                f'the block for {block.name!r} counts {block.failed_count} failures but explains '
                f'{len(block.failures)}')
        unlocated = [item for item in block.failures if item.path is None or item.line is None]
        if unlocated:
            raise KaniLogError(
                f'the block for {block.name!r} explains a failure without a source location: '
                f'{unlocated[0].message!r}')
        # A cover count is printed only when the harness declares a cover, and a
        # declared cover is what a record's success witness rests on. Requiring
        # the line when covers are listed means deleting it is a structural
        # error rather than a quiet loss of the run's only witness evidence.
        if block.covered_total is None and block.covers:
            raise KaniLogError(
                f'the block for {block.name!r} lists {len(block.covers)} covers but has no cover count')
        covers = block.covers
        if block.covered_total is not None and len(covers) != block.covered_total:
            raise KaniLogError(
                f'the block for {block.name!r} counts {block.covered_total} covers but lists {len(covers)}')
        satisfied = sum(1 for item in covers if item.status == 'SATISFIED')
        if block.covered_satisfied is not None and satisfied != block.covered_satisfied:
            raise KaniLogError(
                f'the block for {block.name!r} counts {block.covered_satisfied} satisfied covers but lists '
                f'{satisfied}')
        # `(N undetermined)` counts checks Kani could not decide, and
        # `(N unreachable)` counts ones it never reached. A cover carries the
        # latter on its own line instead, as "N of M cover properties satisfied
        # (U unreachable)", because an unreachable witness is a distinct fact.
        observed_other = sum(1 for item in checks if item.status == OTHER_STATUS.get(block.other_kind, ''))
        if block.other_count not in (0, observed_other):
            raise KaniLogError(
                f'the block for {block.name!r} counts {block.other_count} {block.other_kind} results but '
                f'lists {observed_other}')
        observed_unreachable = sum(1 for item in covers if item.status == 'UNREACHABLE')
        if block.covered_unreachable is not None and block.covered_unreachable != observed_unreachable:
            raise KaniLogError(
                f'the block for {block.name!r} counts {block.covered_unreachable} unreachable covers but '
                f'lists {observed_unreachable}')

    def results(self, block: HarnessBlock) -> None:
        """Consume the ``RESULTS:`` block, which lists every check by number."""
        block.has_results = True
        while not self.exhausted:
            line = self.peek()
            entry = CHECK.match(line)
            if entry is not None:
                block.properties.append(self.check(entry))
            elif not line.strip():
                self.take()
            else:
                return

    def check(self, match: re.Match[str]) -> PropertyResult:
        """Consume the three fields of one ``Check N:`` entry, from its matched line.

        The caller matches the line and passes the match, because re-matching the
        same line here cannot fail: a guard for it would be a refusal no log can
        produce.
        """
        self.take()
        values: dict[str, str] = {}
        while not self.exhausted:
            field_match = FIELD.match(self.peek())
            if field_match is None:
                break
            self.take()
            values[field_match['key']] = field_match['value']
        missing = [key for key in CHECK_FIELDS if key not in values]
        if missing:
            raise KaniLogError(f'{self.where()}: check {match["identifier"]!r} is missing {", ".join(missing)}')
        if values['Status'] not in CHECK_STATUSES:
            raise KaniLogError(
                f'{self.where()}: check {match["identifier"]!r} has unknown status {values["Status"]!r}')
        return PropertyResult(identifier=match['identifier'], status=values['Status'],
                              description=values['Description'].strip('"'))

    def summary(self, block: HarnessBlock) -> None:
        """Consume the ``SUMMARY:`` block, including its failed-check explanations."""
        while not self.exhausted:
            line = self.peek()
            total = TOTAL.match(line)
            cover = COVER.match(line)
            if total is not None:
                if block.failed_count is not None:
                    raise KaniLogError(f'the block for {block.name!r} has two failure counts')
                self.take()
                block.failed_count = int(total['failed'])
                block.total_count = int(total['total'])
                block.other_count = int(total['other'] or 0)
                block.other_kind = total['other_kind']
            elif cover is not None:
                if block.covered_total is not None:
                    raise KaniLogError(f'the block for {block.name!r} has two cover counts')
                self.take()
                block.covered_satisfied = int(cover['satisfied'])
                block.covered_total = int(cover['total'])
                if cover['unreachable'] is not None:
                    block.covered_unreachable = int(cover['unreachable'])
            elif message := FAILED_CHECK.match(line):
                self.take()
                block.failures.append(self.failed_check(message))
            elif VERIFICATION.match(line) or line == UNSUPPORTED_REACHABLE:
                return
            elif not line.strip():
                self.take()
            else:
                raise KaniLogError(
                    f'{self.where()}: unrecognised summary line for {block.name!r}: {line!r}')
        raise KaniLogError(f'the log is truncated inside the summary for {block.name!r}')

    def failed_check(self, match: re.Match[str]) -> FailedCheck:
        """Consume the optional location line that follows a failed-check message."""
        path: str | None = None
        line: int | None = None
        if not self.exhausted:
            location = FAILED_LOCATION.match(self.peek())
            if location is not None:
                self.take()
                path, line = location['path'], int(location['line'])
        return FailedCheck(message=match['message'], path=path, line=line)

    def verification(self, block: HarnessBlock, match: re.Match[str]) -> None:
        """Record the verdict from one already-matched ``VERIFICATION:`` line."""
        self.take()
        if block.verdict is not None:
            raise KaniLogError(f'the block for {block.name!r} reports two verification results')
        block.verdict = match['verdict']
        block.panics_as_expected = match['note'] == '(encountered one or more panics as expected)'

    def manual(self) -> ManualSummary:
        """Consume the ``Manual Harness Summary`` that ends a complete run."""
        self.take()
        failed: list[str] = []
        while not self.exhausted:
            line = self.peek()
            failure = FAILED_FOR.match(line)
            complete = COMPLETE.match(line)
            if failure is not None:
                self.take()
                failed.append(failure['name'])
            elif complete is not None:
                self.take()
                return ManualSummary(int(complete['verified']), int(complete['failures']),
                                     int(complete['total']), tuple(failed))
            elif not line.strip():
                self.take()
            else:
                raise KaniLogError(f'{self.where()}: unrecognised manual summary line: {line!r}')
        raise KaniLogError('the log is truncated: the manual harness summary has no counts')

    def unsupported_constructs(self) -> list[str]:
        """Consume Kani's pre-flight list of constructs it cannot model."""
        self.take()
        names: list[str] = []
        while not self.exhausted:
            entry = UNSUPPORTED_ENTRY.match(self.peek())
            if entry is None:
                if self.peek().strip():
                    return names
                self.take()
                continue
            names.append(entry['name'])
            self.take()
        return names


def is_noise(line: str) -> bool:
    """Report whether a line is build or driver chatter rather than report content.

    The prefixes are deliberately broad: the parser refuses logs it cannot
    explain *inside* a report, and refusing a new Cargo message between reports
    would make it break on every toolchain bump.
    """
    return not line.strip() or line.startswith(NOISE_PREFIXES)
