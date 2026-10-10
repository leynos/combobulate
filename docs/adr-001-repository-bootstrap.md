# ADR 001: Bootstrap the repository from the Rust build baseline

## Status

Accepted on 2026-10-06: adopt the Rust build baseline and Combobulate design
pack for repository setup. The product design remains proposed.

## Date

2026-10-06

## Context

Combobulate needs a reproducible Rust development scaffold before the roadmap's
implementation experiments can begin. Peregrine Web PR #11 supplies pinned
compiler and linker routes, strict lints, coverage publication, and executable
workflow/Make contracts. Its web-framework design does not describe
Combobulate. Its exact head also contains three outstanding CodeScene
complexity findings.

## Decision

Adapt the structure at Peregrine commit
`7a68360fb0ad3e8dfad1d6a22df62a19e41bc486`. Replace product-specific design
material with the supplied Combobulate revision 0.2 documents, specification
fixtures, and generators. Keep the generic Rust engineering references and
build contracts, with Combobulate package identity and contributor guidance.

Repair the long Make command constructor and duplicate test setup through
cohesive, suite-local helpers. Preserve distinct driver and configuration
policy data, missing-versus-null YAML cases, and negative controls. Keep the
lint thresholds and unsuppressed failure semantics.

Run the design-model validator in a separate hosted workflow. Its scope is
documentation/specification consistency; it cannot establish that a Rust API,
backend capability, static cost certificate, or proof works.

## Consequences

The repository can validate its scaffold while the product roadmap remains
open. No Polars or verifier runtime dependency is introduced merely to describe
future functionality. The greeting stub remains temporary. Hosted analysis must
establish the new repository's actual check state; predecessor results do not
confer merge eligibility on this repository.

## References

- [Peregrine Web PR #11](https://github.com/leynos/peregrine-web/pull/11).
- [Technical design](technical-design.md).
- [GIST roadmap](roadmap.md).
