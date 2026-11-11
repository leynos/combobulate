"""Hold the committed harness manifest a Kani decision is taken against.

A log says what happened; it cannot say what was meant to happen. The manifest
supplies the missing half: which harnesses are claims and which are negative
controls, which covers each claim declares, and which property each control is
supposed to fail. It also supplies DL-09's absence rule, because only a bound
claim set can turn a harness missing from the log into ``skipped`` rather than
into silence.

The types live apart from :mod:`~docs_validation.kani_log.decide` so the
decision function reads as the precedence table it implements, and so the
validation a malformed manifest needs is next to the entries it inspects.

Examples
--------
>>> Manifest((Harness('h::x', 'claim'),)).names()
('h::x',)
>>> Harness('h::c', 'control')
Traceback (most recent call last):
ValueError: control 'h::c' names no property it is expected to fail
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

__all__ = ['CLAIM', 'CONTROL', 'ROLES', 'Harness', 'Manifest', 'manifest_from_document']

CLAIM = 'claim'
CONTROL = 'control'
ROLES = frozenset({CLAIM, CONTROL})


@dataclass(frozen=True, slots=True)
class Harness:
    """One manifest entry; e.g. ``Harness('harnesses::x', 'claim', (), None, False)``.

    A control must name the check it is expected to fail, and may not be a
    ``should_panic`` harness: VO-11b reserves that flag for a claim whose
    "failure" is the panic Kani was asked to expect. Refusing both at
    construction keeps them out of the decision rather than making every log
    pay to re-check them.
    """

    name: str
    role: str
    covers: tuple[str, ...] = ()
    expected_failure: str | None = None
    should_panic: bool = False

    def __post_init__(self) -> None:
        """Refuse a manifest entry the decision function could only guess at."""
        if self.role not in ROLES:
            raise ValueError(f'harness {self.name!r} has unknown role {self.role!r}')
        if self.role == CONTROL and self.should_panic:
            raise ValueError(f'control {self.name!r} declares should_panic, which may mark only a claim')
        if self.role == CONTROL and not self.expected_failure:
            raise ValueError(f'control {self.name!r} names no property it is expected to fail')
        if self.role == CLAIM and self.covers and self.should_panic:
            raise ValueError(f'claim {self.name!r} is should_panic, so its covers would be unreachable')


@dataclass(frozen=True, slots=True)
class Manifest:
    """The committed harness manifest: roles, declared covers, expected control failures."""

    harnesses: tuple[Harness, ...]

    @property
    def claims(self) -> tuple[Harness, ...]:
        """Return the harnesses whose success the evidence may rest on."""
        return tuple(item for item in self.harnesses if item.role == CLAIM)

    @property
    def controls(self) -> tuple[Harness, ...]:
        """Return the negative controls, which must fail for the declared reason."""
        return tuple(item for item in self.harnesses if item.role == CONTROL)

    def names(self) -> tuple[str, ...]:
        """Return every declared harness name in manifest order."""
        return tuple(item.name for item in self.harnesses)

    def declared_covers(self) -> tuple[str, ...]:
        """Return every cover description a claim declares, in manifest order."""
        return tuple(cover for item in self.claims for cover in item.covers)

    def select(self, names: tuple[str, ...]) -> Manifest:
        """Narrow the manifest to the harnesses one record claims.

        A committed manifest describes a whole crate; a record asserts some of
        it. Decision facts are per-record, so the manifest a record binds is
        this narrowing: the roles are unchanged, the claim set shrinks to what
        the record asserts, and any other harness the log reports becomes a
        structural error because the record never claimed it.

        Parameters
        ----------
        names
            Harness names the record claims, in the order it lists them.

        Returns
        -------
        Manifest
            The narrowed manifest, in the order ``names`` gives.

        Raises
        ------
        ValueError
            If a name is not in this manifest, or is named twice.

        Examples
        --------
        ``Manifest((Harness('h::a', 'claim'), Harness('h::b', 'control', (), 'assertion.1')))
        .select(('h::a',))`` leaves one claim and no control.
        """
        by_name = {item.name: item for item in self.harnesses}
        unknown = [name for name in names if name not in by_name]
        if unknown:
            raise ValueError(f'the manifest does not declare {unknown}')
        if len(set(names)) != len(names):
            raise ValueError(f'the selection names a harness twice: {list(names)}')
        return Manifest(tuple(by_name[name] for name in names))


def manifest_from_document(document: Mapping[str, object]) -> Manifest:
    """Build a manifest from the committed JSON a verification record binds.

    Parameters
    ----------
    document
        A mapping with a ``harnesses`` array; each entry names ``name``,
        ``role``, and, for a control, the ``expected_failure`` check it must
        fail. ``covers`` and ``should_panic`` default to empty and false.

    Returns
    -------
    Manifest
        The manifest the decision function consumes.

    Raises
    ------
    ValueError
        If the document, or any entry in it, does not describe a harness the
        decision can be taken against.

    Examples
    --------
    ``manifest_from_document({'harnesses': [{'name': 'h::x', 'role': 'claim'}]})``
    yields a one-claim manifest with no declared cover.
    """
    entries = document.get('harnesses')
    if not isinstance(entries, list):
        raise ValueError('the harness manifest has no harnesses array')
    harnesses = []
    for entry in entries:
        if not isinstance(entry, Mapping) or not isinstance(entry.get('name'), str) or not isinstance(
                entry.get('role'), str):
            raise ValueError(f'harness manifest entry {entry!r} does not name a harness and a role')
        covers = entry.get('covers', [])
        if not isinstance(covers, list) or not all(isinstance(item, str) for item in covers):
            raise ValueError(f'harness {entry["name"]!r} has a malformed covers list')
        expected = entry.get('expected_failure')
        if expected is not None and not isinstance(expected, str):
            raise ValueError(f'harness {entry["name"]!r} has a malformed expected_failure')
        # `should_panic` is what lets a failed claim be excused, so a truthful
        # type matters more here than anywhere else in the entry: `bool()` would
        # accept the string "false" as a panic claim.
        should_panic = entry.get('should_panic', False)
        if not isinstance(should_panic, bool):
            raise ValueError(f'harness {entry["name"]!r} has a malformed should_panic')
        harnesses.append(Harness(entry['name'], entry['role'], tuple(covers), expected,
                                 should_panic))
    if not harnesses:
        raise ValueError('the harness manifest declares no harnesses')
    names = [item.name for item in harnesses]
    if len(set(names)) != len(names):
        raise ValueError('the harness manifest declares a harness twice')
    return Manifest(tuple(harnesses))
