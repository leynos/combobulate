# Architectural decision record (ADR) 0004: Licence and publication

## Status

Accepted on 2026-10-10: Combobulate is ISC-licensed, and the crate is not
published to crates.io until the Core acceptance dossier passes and `leynos`
approves release. Records D04 and D05 in the
[decision register](../decision-register.md).

## Date

2026-10-10.

## Context and problem statement

Terms of reference Q7 asked which package licence and external publication
policy apply. The repository bootstrap (ADR-0001) already used ISC in
`Cargo.toml`, `LICENSE`, and `README.md`, but nobody had ratified it, and
nothing prevented an accidental `cargo publish` of a library whose design is
still proposed.

## Decision outcome

- Licence (D04). Ratify ISC. No file changes are needed to adopt it.
- Publication (D05). `Cargo.toml` sets `publish = false`. The flag is removed
  only after the Core acceptance dossier (task 4.3.3) passes and the D01
  authority approves release; that approval is recorded as a superseding
  decision in the register, and the removal lands in the same pull request.

## Consequences

- `cargo publish` refuses to run, so a mistaken publication cannot happen.
- The design checks require `license = "ISC"` and `publish = false` in
  `Cargo.toml` while D04 and D05 stand.
- The developers' guide states the policy and the approval route.
