# Architectural decision record (ADR) 0005: Pre-1.0 API and proof-interface policy

## Status

Accepted on 2026-10-10: no compatibility shims for pre-1.0 or unreleased APIs;
Cargo's 0.y.z rule governs breaking changes; the public proof interface is
versioned with the crate. Records D06 in the
[decision register](../decision-register.md).

## Date

2026-10-10.

## Context and problem statement

Terms of reference constraint C5 and technical design §15 (row 10) proposed
that draft APIs change atomically rather than through aliases and shims.
Combobulate also exposes a public proof interface: logical models, pre- and
postconditions, lemmas, and trust declarations on which downstream proofs
depend (technical design §17.8). A change to that interface can break a
downstream proof without changing any Rust signature, so ordinary API
versioning alone would not signal it.

## Decision outcome

- No compatibility machinery for pre-1.0 or unreleased APIs: no aliases,
  deprecated shims, or dual-format readers. Domain adapters with real semantic
  jobs are not shims.
- Follow Cargo's 0.y.z rule: a change to the leftmost non-zero version
  component is breaking.
- Version the public proof interface with the crate. A strengthened
  precondition or a weakened postcondition is a breaking change even when no
  Rust signature changes.
- The minimum supported Rust version stays with terms of reference Q3 and task
  1.2.1.

## Consequences

- Adopters update against the chosen contract; release notes must state proof
  interface changes alongside API changes.
- Compatibility review covers specifications as well as signatures, which the
  evidence-gate work in task 1.1.4 makes checkable.
