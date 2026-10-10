# Architectural decision record (ADR) 0003: Initial release scope

## Status

Accepted on 2026-10-10: the Core, Integration, and Deferred scope classes in
technical design §2 are the initial release boundary, unchanged. Records D03 in
the [decision register](../decision-register.md).

## Date

2026-10-10.

## Context and problem statement

The language reference catalogues far more operations than a first release
should promise. Technical design §2 proposed three scope classes so that the
catalogue could not become an accidental single-release commitment, and terms
of reference Q4 asked whether that split was the intended release boundary.
Until it was accepted, every roadmap phase and every catalogue entry carried an
unresolved question about whether it was in scope.

## Decision outcome

Accept the split unchanged:

- Core: the initial numeric-language release, delivered and accepted through
  roadmap phases 1 to 4 and the Core acceptance dossier (task 4.3.3).
- Integration: the explicitly gated typed-cell and segmented workstreams, which
  do not enlarge the first release.
- Deferred: proposals that remain outside both, listed after the catalogue
  tables rather than presented as available operations.

## Consequences

- Each catalogue entry keeps its scope label, and the design checks continue
  to require that every Core entry maps to a Core implementation task.
- Moving an operation between classes is a scope change, accepted only by the
  D01 authority through a superseding decision.
- The API inside each class remains proposed; this decision fixes the release
  boundary, not the signatures.
