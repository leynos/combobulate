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
- [Bootstrap decision](adr-001-repository-bootstrap.md): scaffold provenance,
  repository integration, and complexity repair boundaries.

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
