"""Name the grammar of one Kani log and the small facts inside it.

This is the vocabulary half of :mod:`docs_validation.kani_log.extract`: every
regular expression, literal marker, and accepted status the parser recognises,
together with the two leaf value types a single line can produce. Keeping it
separate means the grammar can be compared against a new Kani release without
reading the cursor logic, and that the parser module stays within the
repository's file-size limit.

The grammar was read from the committed corpus in
``scripts/tests/fixtures/kani_logs`` rather than from Kani's documentation, so
it describes what the pinned release actually printed. A Kani log interleaves
three layers: the driver's banner and ``[Kani] Running:`` commands, the Cargo
noise around the build, and the regular-format report
(``Checking harness`` / ``RESULTS:`` / ``SUMMARY:`` / ``VERIFICATION:``). Only
the third layer carries verdicts.

Examples
--------
>>> release = next(iter(SUPPORTED_VERSIONS))
>>> BANNER.match(f'Kani Rust Verifier {release} (cargo plugin)')['version'] == release
True
>>> PropertyResult('harnesses::x.cover.1', 'SATISFIED', 'x').is_cover
True
"""
from __future__ import annotations

import re
from dataclasses import dataclass

BANNER = re.compile(r'^Kani Rust Verifier (?P<version>\d+\.\d+\.\d+) \((?P<kind>[^)]+)\)$')
# The grammar below was read from this release's own output, and a log from a
# different release may print checks, counts, or wording it does not cover. A
# log that names another version is therefore not "a log this parser read and
# disliked" but one it was never written for, so it is refused rather than
# guessed at. Widening this set is a deliberate act: compare the new release's
# output against the committed corpus first.
SUPPORTED_VERSIONS: frozenset[str] = frozenset({'0.67.0'})
HARNESS_START = re.compile(r'^Checking harness (?P<name>[A-Za-z0-9_:.<>]+)\.\.\.$')
VERIFICATION = re.compile(r'^VERIFICATION:- (?P<verdict>SUCCESSFUL|FAILED)(?: (?P<note>\(.*\)))?$')
VERIFICATION_TIME = re.compile(r'^Verification Time: \d+(?:\.\d+)?s$')
CHECK = re.compile(r'^Check (?P<number>\d+): (?P<identifier>\S+)$')
FIELD = re.compile(r'^\t - (?P<key>Status|Description|Location): (?P<value>.*)$')
TOTAL = re.compile(r'^ \*\* (?P<failed>\d+) of (?P<total>\d+) failed'
                   r'(?: \((?P<other>\d+) (?P<other_kind>[a-z]+)\))?$')
COVER = re.compile(r'^ \*\* (?P<satisfied>\d+) of (?P<total>\d+) cover properties satisfied'
                   r'(?: \((?P<unreachable>\d+) unreachable\))?$')
COMPLETE = re.compile(r'^Complete - (?P<verified>\d+) successfully verified harnesses, '
                      r'(?P<failures>\d+) failures, (?P<total>\d+) total\.$')
FAILED_FOR = re.compile(r'^Verification failed for - (?P<name>\S+)$')
FAILED_CHECK = re.compile(r'^Failed Checks: (?P<message>.*)$')
FAILED_LOCATION = re.compile(r'^ File: "(?P<path>[^"]+)", line (?P<line>\d+), in (?P<function>\S+)$')
UNSUPPORTED_ENTRY = re.compile(r'^ +- (?P<name>[A-Za-z0-9_:]+) \(\d+\)$')

LIST_WRITTEN = 'Wrote list results to '
UNSUPPORTED_PRELUDE = 'warning: Found the following unsupported constructs:'
UNWINDING_FAILED = '[Kani] info: Verification output shows one or more unwinding failures.'
UNSUPPORTED_REACHABLE = ('** WARNING: A Rust construct that is not currently supported by Kani was found '
                         'to be reachable. Check the results for more details.')
# The driver echoes the solver command it runs. It is the only place a log
# records what CBMC was asked for, so the decision function reads it rather
# than inferring the setting from a failure. The pinned Kani does *not* pass
# `--unwinding-assertions` at all: CBMC generates unwinding assertions whenever
# it is given a bound, and the driver disables them with
# `--no-unwinding-assertions`. A probe of the pinned CBMC confirmed that
# `cbmc --unwind 1 loop.c` reports `unwinding assertion loop 0: FAILURE` while
# `cbmc loop.c` reports none, so the presence of `--unwind`/`--unwindset` is
# what decides whether the check ran.
SOLVER_COMMAND = '[Kani] Running: `cbmc '
UNWINDING_BOUND_FLAGS = (' --unwind ', ' --unwindset ')
NO_UNWINDING_ASSERTIONS_FLAG = ' --no-unwinding-assertions'
TIMED_OUT = 'CBMC timed out.'
CBMC_FAILED = 'CBMC failed'
# Kani's own wording when it reaches a construct it cannot model. The corpus's
# ``unsupported`` log fails the harness's assertion with this phrase rather than
# an ``unsupported_construct`` check, so the phrase is the only distinguishing
# evidence for that shape.
UNSUPPORTED_MARKER = 'not currently supported by kani'
CHECK_FIELDS = ('Status', 'Description', 'Location')
CHECK_STATUSES = frozenset({'SUCCESS', 'FAILURE', 'UNDETERMINED', 'UNREACHABLE', 'SATISFIED', 'UNSATISFIABLE'})
# Map the word Kani prints in parentheses to the status the checks carry.
OTHER_STATUS = {'undetermined': 'UNDETERMINED', 'unreachable': 'UNREACHABLE'}
COVER_KIND = 'cover'
UNWINDING_KIND = 'unwind'
UNSUPPORTED_KIND = 'unsupported_construct'
NOISE_PREFIXES = (
    '[Kani] ', 'warning: ', '   ', '    ', 'Finished ', 'Reading ', 'Writing ', 'Adding ', 'Removing ',
    'Cleaning ', 'Function ', 'Virtual ', 'Trying ', 'Generating ', 'Running ', 'Passing ',
    'Converting ', 'Solving ', 'SAT ', 'Generic ', 'CBMC ', 'Runtime ', 'size of ', 'slicing ',
    'Generated ', 'generate function bodies: ', 'aborting path on assume', 'Unwinding loop ',
    'Not unwinding loop ', 'Removal of ', '---', 'INFO ', '======', 'Total #', '  - ',
    'Reachable Items:',
)


class KaniLogError(ValueError):
    """A log the parser cannot account for; VO-11b maps this to ``tool-error``."""

    def __init__(self, reason: str) -> None:
        """Record the structural reason, which every caller must report."""
        super().__init__(f'structural error: {reason}')
        self.reason = reason


@dataclass(frozen=True, slots=True)
class PropertyResult:
    """One ``Check N:`` entry; e.g. ``PropertyResult('h::x.cover.1', 'SATISFIED', ...)``.

    The ``Location`` field is parsed and required — a check without one is a
    structural error — but its value is not kept. Nothing reads it, and the
    source locations a record can cite come from the `` File:`` lines beneath
    the failures, which :class:`FailedCheck` does keep.
    """

    identifier: str
    status: str
    description: str

    @property
    def kind(self) -> str:
        """Name the check class from its identifier suffix.

        Kani ends a check identifier with the property it reports, so
        ``harnesses::x.unwind.0`` is an unwinding check and
        ``harnesses::x.cover.1`` a witness, whatever the status says.
        Classifying by identifier rather than description keeps a seeded
        mutation from relabelling a check by editing prose.
        """
        parts = self.identifier.split('.')
        return parts[-2] if len(parts) >= 3 else ''

    @property
    def is_cover(self) -> bool:
        """Report whether this check is a declared success witness."""
        return self.kind == COVER_KIND

    @property
    def is_unwinding(self) -> bool:
        """Report whether this check is an unwinding assertion."""
        return self.kind == UNWINDING_KIND

    @property
    def owner(self) -> str | None:
        """Return the harness this check belongs to, or None when it names none."""
        parts = self.identifier.split('.')
        return '.'.join(parts[:-2]) if len(parts) >= 3 else None

    @property
    def property(self) -> str:
        """Name the property within its harness, such as ``assertion.1`` or ``unwind.0``.

        This is the part of the identifier a manifest can name without repeating
        the harness, which is how a control states the property it must fail.
        """
        parts = self.identifier.split('.')
        return '.'.join(parts[-2:]) if len(parts) >= 2 else self.identifier


@dataclass(frozen=True, slots=True)
class FailedCheck:
    """One ``Failed Checks:`` entry; e.g. ``FailedCheck('unwinding assertion loop 0', 'src/x.rs', 7)``."""

    message: str
    path: str | None
    line: int | None
