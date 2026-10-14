# Documentation contents

[Documentation contents](contents.md).

This index covers Combobulate's proposed design and current development
scaffold. Design entries describe intended behaviour; they do not establish an
implemented API or completed verification.

## Product direction and design

- [Terms of reference](terms-of-reference.md): problem, users, goals, scope,
  constraints, and open decisions.
- [Context and ubiquitous language](context.md): vocabulary and boundaries.
- [Technical design](technical-design.md): array semantics, architecture,
  human-readable diagnostics, proof-first/public contracts, compile-time
  costing, and Polars capabilities.
- [Initial language reference](language-reference.md): verbs, conjunctions,
  modifiers, macros, and proposed execution/proof interfaces.
- [GIST roadmap](roadmap.md): Goals, Ideas, Steps, and Tasks, with dependencies
  and observable acceptance criteria.
- [Testable bets](testable-bets.md): experiments and explicit falsifiers.
- [Revision 0.2](revision-0.2.md): changes from the original design.
- [Source register](references.md): technical sources and evidence limits.
- [Design validation](validation.md): documentation checks and outstanding
  implementation/verifier obligations.
- [Acceptance calibration](acceptance-calibration.md): measurements and
  extrapolation behind the pre-registered acceptance-control thresholds.
- [Evidence and decision records](evidence-and-decision-records.md): schemas,
  admission levels, reason codes, and producer obligations for governance
  records.
- [Decision register](decision-register.md): decisions that control
  acceptance, their authority, options, approval references, and ADRs.
- [ADR-0001: repository bootstrap](adrs/adr-0001-repository-bootstrap.md):
  scaffold provenance, repository integration, and complexity repair boundaries.
- [ADR-0002: governance authority and exceptions](adrs/adr-0002-governance-authority.md).
- [ADR-0003: initial release scope](adrs/adr-0003-initial-release-scope.md).
- [ADR-0004: licence and publication](adrs/adr-0004-licence-and-publication.md).
- [ADR-0005: pre-1.0 API and proof-interface policy](adrs/adr-0005-pre-1-0-api-and-proof-interface-policy.md).
- [ADR-0006: numeric, validity, and reduction contracts](adrs/adr-0006-numeric-validity-and-reduction-contracts.md).
- [ADR-0007: `comb!` macro grammar and staging](adrs/adr-0007-comb-macro-grammar-and-staging.md).
- [ADR-0008: acceptance-control pre-registration](adrs/adr-0008-acceptance-control-pre-registration.md).
- [ADR-0009: proof-first policy and evidence gate](adrs/adr-0009-proof-first-policy-and-evidence-gate.md).

## Execution plans

- [Roadmap 1.1: resolve the decisions that control acceptance](execplans/1-1-resolve-acceptance-control-decisions.md):
  ExecPlan for roadmap step 1.1, implemented in stacked pull requests.

## Project guides

- [User guide](users-guide.md): current availability and design examples.
- [Developer guide](developers-guide.md): contributor workflow and tooling.
- [Repository layout](repository-layout.md): paths and ownership boundaries.
- [Documentation style guide](documentation-style-guide.md): spelling,
  Markdown, ADR, RFC, and roadmap conventions.

## Rust reference material

- [Reliable testing through dependency injection](reliable-testing-in-rust-via-dependency-injection.md).
- [Rust doctest DRY guide](rust-doctest-dry-guide.md).
- [Rust testing with rstest fixtures](rust-testing-with-rstest-fixtures.md).
- [rstest-bdd user guide](rstest-bdd-users-guide.md).

## Engineering practice

- [Complexity antipatterns and refactoring strategies](complexity-antipatterns-and-refactoring-strategies.md).
- [Scripting standards](scripting-standards.md).

## Machine-readable design

The [specification directory](../spec/) contains vocabulary, examples, roadmap,
traceability, proof obligations/evidence schemas, cost cases, kernel contracts,
and backend capability plans. [Validation results](validation-results.json)
record the documentation model's latest execution, not Rust proof results.
[Revision comparison](revision-comparison.json) records the imported revision's
scope changes.
