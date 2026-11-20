"""Read a Verus log as the diagnostics it reported, each with its location.

A Verus diagnostic is two facts that only mean something together: the `error:`
text it printed and the ``-->`` line it refers to. A rule that keeps only the
text cannot tell a failure in the mutant it is qualifying from one in a
neighbouring wrapper, and a rule that keeps only the locations cannot tell an
invariant failure from an assertion. This module owns that pairing, so the
verdict rules in :mod:`verus_kernel_verdicts` can ask about failures rather than
about lines.

Nothing here runs a solver or writes anything. The only filesystem access is
the marker table, which names the checkout a committed log was rewritten
against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_LOCATION = re.compile(r"(?m)^\s*-->\s*(?P<path>.+?):(?P<line>\d+):(?P<column>\d+)$")

# The checkout the committed logs were rewritten against. ``kernel_record``
# replaces the repository root and the home directory with markers so a record
# does not describe one host, so a rule reading a committed log has to put them
# back before it can tell which file a diagnostic names.
_MARKERS = (("<repo>", Path(__file__).resolve().parents[1]), ("~", Path.home()))


@dataclass(frozen=True)
class Diagnostic:
    """One Verus diagnostic: the error it printed and the line it named.

    The location may be absent, because Verus can report an obligation it could
    not locate. Keeping the two facts together is what stops a located failure
    from explaining an unlocated one that happens to share its wording.
    """

    text: str
    path: Path | None = None
    line: int | None = None

    @property
    def is_abort_summary(self) -> bool:
        """Report whether this is Verus's count of the errors above it."""
        return self.text.startswith("error: aborting due to")

    def names(self, source: Path) -> bool:
        """Report whether this diagnostic names a line of ``source``.

        The comparison is on the full path, not the file name: a copy of the
        mutant root in a scratch directory has the same base name and would
        otherwise satisfy a rule about the file the driver compiled.
        """
        return self.location_in(source) is not None

    def location_in(self, source: Path) -> int | None:
        """Return the line this diagnostic names inside ``source``, if any."""
        if self.path is None or self.line is None:
            return None
        if _resolved(self.path) != _resolved(source):
            return None
        return self.line


def diagnostics(log: str) -> list[Diagnostic]:
    """Pair each ``error:`` line with the ``-->`` location that follows it.

    Verus prints an error, then a source excerpt, and the location somewhere
    near the top of that excerpt; a diagnostic's location is the first one
    printed after the error and before the next error. A replaced location
    starts a new excerpt rather than describing the same failure, so only the
    first is kept. An error with no location at all is still a diagnostic, and
    is reported without one.
    """
    found: list[Diagnostic] = []
    pending: str | None = None
    for line in log.splitlines():
        if line.startswith("error:"):
            if pending is not None:
                found.append(Diagnostic(pending))
            pending = line
        elif pending is not None and (match := _LOCATION.match(line)) is not None:
            found.append(Diagnostic(pending, Path(match["path"]), int(match["line"])))
            pending = None
    if pending is not None:
        found.append(Diagnostic(pending))
    return found


def texts(items: list[Diagnostic]) -> list[str]:
    """Return the error texts ``items`` reported, in the order they printed."""
    return [item.text for item in items]


def _resolved(path: Path) -> Path:
    """Return the absolute path ``path`` names, with the portable markers applied.

    A captured log is rewritten before it is committed, so the same file is
    spelled ``<repo>/crates/…`` in the record and ``/home/…/crates/…`` in a
    fresh run. Restoring the markers is what lets one rule qualify both without
    accepting a path that merely ends in the same file name.
    """
    text = str(path)
    for marker, replacement in _MARKERS:
        text = text.replace(marker, str(replacement))
    return Path(text).resolve()
