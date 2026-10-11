# Decision register

This register records the decisions that control acceptance of Combobulate
work: who may accept architecture, scope, and release readiness; which policies
govern licence, publication, compatibility, and trusted-boundary exceptions;
which semantic contracts the implementation must satisfy; and how acceptance
experiments are measured. It answers the open questions in
[terms of reference §9](terms-of-reference.md#9-open-questions) that block
implementation acceptance: Q1, Q2, Q4, Q7, and Q8.

## How to read and change the register

Each decision has a lifecycle of `proposed`, `accepted`, `superseded`, or
`withdrawn`. Only the authority named by D01 can accept a decision; an agent or
contributor drafts and recommends but never accepts. An accepted record names
the chosen option, the date, the accepting login, and a structured approval
reference: a session answer (quoted verbatim), a pull request review, a pull
request comment, or a commit. An ambiguous approval accepts nothing. The
sponsor's merge of the pull request that records an acceptance is its durable
confirmation.

Accepting a decision is not verification. No accepted decision changes a proof
obligation's status, marks a bet as run, or makes a capability eligible. A
substantive decision is explained in an ADR under `docs/adrs/`; the record
links it. An accepted decision is never edited in place: it is replaced by a
new record that supersedes it, so its history remains readable.

The content between the generated markers below is rendered from
`spec/decisions.json` (validated by `spec/decision-register.schema.json`). Edit
the JSON master, then run `scripts/generate_decisions.py`; the design checker
fails when this document has drifted from the master.

<!-- decisions:start -->

## Decisions

### D01

Subject: Decision authority for architecture, scope, release readiness,
exceptions, and proof-API changes.

Terms-of-reference questions: Q1, Q8. Authority: sponsor.

Lifecycle: accepted.

Options:

- A. The sponsor alone accepts every decision.
- B. The sponsor plus a named technical owner, who may be the same person, with
  delegated acceptance of contract records and pre-registrations. (recommended)

Recommendation rationale: Terms of reference §9 already names "Sponsor and
technical owner" as the authority for Q2 and Q4; choosing the sponsor alone
would require amending that column.

Decision: option B, accepted on 2026-10-10 by `leynos`
([session answer](https://lody.ai/leynos/sessions/99861d46-f6f5-48d6-acfb-658bee9364bf)).
Answer: "Sponsor and technical owner @leynos"

ADR: [ADR-0002](adrs/adr-0002-governance-authority.md).

### D02

Subject: Trusted-boundary exception policy.

Terms-of-reference questions: Q8. Authority: sponsor.

Lifecycle: accepted.

Options:

- A. An exception is valid from its approval date until its `invalid_from` date,
  at most 90 days and never past the next release-gate task (4.3.3 or 6.3.4);
  renewal is a new approval; an exception names a narrowed claim and can never
  satisfy a proof-required component. (recommended)

Recommendation rationale: Bounded lifetimes force each exception to be
revisited, and a narrowed claim keeps an exception from being read as proof
(technical design §17.2, GAP9).

Decision: option A, accepted on 2026-10-10 by `leynos`
([session answer](https://lody.ai/leynos/sessions/99861d46-f6f5-48d6-acfb-658bee9364bf)).
Answer: "Accepted"

ADR: [ADR-0002](adrs/adr-0002-governance-authority.md).

### D03

Subject: Initial release scope.

Terms-of-reference questions: Q4. Authority: sponsor, technical owner.

Lifecycle: accepted.

Options:

- A. Accept the Core, Integration, and Deferred split in technical design §2
  unchanged. (recommended)
- B. Amend the scope matrix in technical design §2 before acceptance.

Recommendation rationale: The split already maps every requirement to a roadmap
phase and keeps integration work out of the Core acceptance dossier.

Decision: option A, accepted on 2026-10-10 by `leynos`
([session answer](https://lody.ai/leynos/sessions/99861d46-f6f5-48d6-acfb-658bee9364bf)).
Answer: "Accepted"

ADR: [ADR-0003](adrs/adr-0003-initial-release-scope.md).

### D04

Subject: Package licence.

Terms-of-reference questions: Q7. Authority: sponsor.

Lifecycle: accepted.

Options:

- A. Ratify the ISC licence already recorded in `Cargo.toml`, `LICENSE`, and
  `README.md`. (recommended)

Recommendation rationale: ISC is permissive and is already in place through
ADR-0001; ratification removes the open question without changing any file.

Decision: option A, accepted on 2026-10-10 by `leynos`
([session answer](https://lody.ai/leynos/sessions/99861d46-f6f5-48d6-acfb-658bee9364bf)).
Answer: "Accepted"

ADR: [ADR-0004](adrs/adr-0004-licence-and-publication.md).

### D05

Subject: External publication policy.

Terms-of-reference questions: Q7. Authority: sponsor.

Lifecycle: accepted.

Options:

- A. Set `publish = false` in `Cargo.toml` until the Core acceptance dossier
  (task 4.3.3) passes and the D01 authority approves release. (recommended)

Recommendation rationale: Publication before the Core dossier would promise
distribution terms for an unproven library.

Decision: option A, accepted on 2026-10-10 by `leynos`
([session answer](https://lody.ai/leynos/sessions/99861d46-f6f5-48d6-acfb-658bee9364bf)).
Answer: "Accepted. Ensure this is clearly documented in the developer's guide."

ADR: [ADR-0004](adrs/adr-0004-licence-and-publication.md).

### D06

Subject: Pre-1.0 API and public proof-interface compatibility policy.

Terms-of-reference questions: none. Authority: sponsor, technical owner.

Lifecycle: accepted.

Options:

- A. Ratify ToR C5 and technical design §15 row 10 (no shims for pre-1.0 or
  unreleased APIs); follow Cargo's 0.y.z rule (a change to the leftmost
  non-zero component is breaking); version the public proof interface (models,
  pre- and postconditions, lemmas, trust declarations) with the crate version,
  treating a strengthened precondition or weakened postcondition as breaking
  (technical design §17.8). MSRV stays with ToR Q3 and task 1.2.1. (recommended)

Recommendation rationale: It applies the existing no-compatibility-machinery
constraint to both the Rust API and the proof interface that downstream proofs
depend on.

Decision: option A, accepted on 2026-10-10 by `leynos`
([session answer](https://lody.ai/leynos/sessions/99861d46-f6f5-48d6-acfb-658bee9364bf)).
Answer: "Accepted"

ADR: [ADR-0005](adrs/adr-0005-pre-1-0-api-and-proof-interface-policy.md).

### D07

Subject: Dispositions of the candidate ADR subjects.

Terms-of-reference questions: none. Authority: sponsor, technical owner.

Lifecycle: accepted.

Options:

- A. Numerical and array semantics to ADR-0006; macro staging and stable-Rust
  application to ADR-0007; initial release scope to ADR-0003; public proof
  compatibility to ADR-0005 and ADR-0009; shared semantic kernel and backend
  and cell separation deferred to task 1.2.1 (B01 can falsify the kernel in
  1.2.4); resource certification deferred to step 2.4 (B03); backend input and
  output control scope deferred to task 1.2.6 (B06). (recommended)

Recommendation rationale: Each subject is decided where its evidence arises;
subjects that depend on unrun bets are deferred to the tasks that run them.

Decision: option A, accepted on 2026-10-10 by `leynos`
([session answer](https://lody.ai/leynos/sessions/99861d46-f6f5-48d6-acfb-658bee9364bf)).
Answer: "Accepted. Please update the documentation style guide to place ADRs in
`docs/adrs/` with naming pattern `adr-nnnn-foo-bar-qux.md` where `nnnn` is a
four digit index and `foo-bar-qux` is the title slug. Similarly, RFCs in
`docs/rfcs/` with naming pattern `rfc-nnnn-foo-bar-qux.md`  This breaks from
current DF12 standards, but the current practice is really starting to bug me
and I want to take this opportunity to revise it. If it goes well, we will
update the centralized documentation style guide in `agent-helper-scripts`
documentation library."

ADR: none yet.

### D08

Subject: `comb!` operator precedence.

Terms-of-reference questions: none. Authority: technical owner.

Lifecycle: accepted.

Options:

- A. Rust's expression precedence as parsed by `syn`, with `|>` split from the
  token stream first (lowest precedence, left-associative); reject, with a
  first-screen diagnostic, any comparison that is the unparenthesized operand of
  `&`, `|`, or `^` and vice versa; translate the chained-comparison error from
  `syn` into the same diagnostic. (recommended)

Recommendation rationale: Reusing Rust precedence keeps `comb!` readable to
Rust developers, and rejecting comparison mixed with bitwise operators removes
the one precedence trap Rust users commonly misread.

Decision: option A, accepted on 2026-10-10 by `leynos`
([session answer](https://lody.ai/leynos/sessions/99861d46-f6f5-48d6-acfb-658bee9364bf)).
Answer: "Accepted"

ADR: [ADR-0007](adrs/adr-0007-comb-macro-grammar-and-staging.md).

### D09

Subject: F64 special values in reductions and binary `min` and `max`.

Terms-of-reference questions: none. Authority: technical owner.

Lifecycle: accepted.

Options:

- A. Binary `min` and `max` follow IEEE 754-2019 `minimum` and `maximum` (NaN
  propagates; negative zero is less than positive zero); null propagation takes
  precedence over NaN; an empty F64 `sum` returns positive zero (the registered
  typed zero) while `sum([-0.0])` returns negative zero (a singleton passes
  through); a `mean` count of exactly 2^53 is admitted. (recommended)

Recommendation rationale: IEEE 754-2019 `minimum` and `maximum` are total and
deterministic, unlike the NaN-ignoring `minNum` and `maxNum` operations.

Decision: option A, accepted on 2026-10-10 by `leynos`
([session answer](https://lody.ai/leynos/sessions/99861d46-f6f5-48d6-acfb-658bee9364bf)).
Answer: "Accepted"

ADR: [ADR-0006](adrs/adr-0006-numeric-validity-and-reduction-contracts.md).

### D10

Subject: Typed-cell atomicity.

Terms-of-reference questions: none. Authority: technical owner.

Lifecycle: accepted.

Options:

- A. Record two distinct rules under distinct names: cell atomicity (a typed
  cell such as `DVec3` is one logical element until an explicit component
  operation; `Batch<DVec3>` of shape `[2,3]` has cardinality 6) and atomic
  output commit (failure or cancellation before commit leaves the destination
  unchanged). (recommended)

Recommendation rationale: The single phrase "typed-cell atomicity" had been
used for two unrelated guarantees.

Decision: option A, accepted on 2026-10-10 by `leynos`
([session answer](https://lody.ai/leynos/sessions/99861d46-f6f5-48d6-acfb-658bee9364bf)).
Answer: "Accepted"

ADR: [ADR-0006](adrs/adr-0006-numeric-validity-and-reduction-contracts.md).

### D11

Subject: Acceptance measurement environments.

Terms-of-reference questions: Q2. Authority: sponsor, technical owner.

Lifecycle: proposed.

Options:

- A. A named, otherwise idle reference machine (CPU model, cores, memory,
  governor, SMT, kernel, isolation).
- B. Paired, interleaved runs within one hosted job on a pinned `ubuntu-24.04`
  runner class, with instruction counts as the primary metric and wall time
  secondary; proof and build ceilings use the same runner class; shared
  development hosts are never acceptance environments. (recommended)

Recommendation rationale: The hosted paired design needs no dedicated hardware
and controls drift by interleaving.

Decision: pending.

ADR: none yet.

### D12

Subject: Acceptance thresholds and statistics.

Terms-of-reference questions: Q2. Authority: sponsor, technical owner.

Lifecycle: proposed.

Options:

- A. The sponsor supplies or amends every threshold value in the
  pre-registration proposal. (recommended)
- B. Delegate threshold selection to calibration: realistic measurements on the
  development machine, extrapolated to the hosted runner class, with the
  evidence recorded.

Recommendation rationale: Thresholds govern acceptance, so the planning agent
did not choose them itself.

Decision: pending.

ADR: none yet.

### D13

Subject: Governance enforcement.

Terms-of-reference questions: none. Authority: sponsor.

Lifecycle: accepted.

Options:

- A. Commit `.github/CODEOWNERS` naming the D01 logins for the decision,
  exception, acceptance-control, and semantic-contract registers and the ADRs,
  with required code-owner review and a required Design contracts check on
  main. (recommended)
- B. No `CODEOWNERS` file; the base-revision freeze check and the sponsor's pull
  request review and merge are the controls, revisited if another developer
  joins.

Recommendation rationale: Code-owner review would make an unauthorized register
edit a blocked merge rather than a reviewer catch.

Decision: option B, accepted on 2026-10-10 by `leynos`
([session answer](https://lody.ai/leynos/sessions/99861d46-f6f5-48d6-acfb-658bee9364bf)).
Answer: "No, we don't do `.github/CODEOWNERS`. If we magically acquire another
dev, we can change this."

ADR: [ADR-0002](adrs/adr-0002-governance-authority.md).

### D14

Subject: `div` on I64 operands.

Terms-of-reference questions: none. Authority: technical owner.

Lifecycle: accepted.

Options:

- A. Convert each operand to F64 (round to nearest, ties to even), then apply
  IEEE division, matching Rust `as f64` and common backends; document that this
  can differ from rounding the exact quotient once. (recommended)

Recommendation rationale: Technical design §6.1 says only "true division to
F64"; converting operands first matches what every candidate backend computes.

Decision: option A, accepted on 2026-10-10 by `leynos`
([session answer](https://lody.ai/leynos/sessions/99861d46-f6f5-48d6-acfb-658bee9364bf)).
Answer: "Accepted"

ADR: [ADR-0006](adrs/adr-0006-numeric-validity-and-reduction-contracts.md).

### D15

Subject: Prospective details for later roadmap tasks.

Terms-of-reference questions: none. Authority: sponsor, technical owner.

Lifecycle: proposed.

Options:

- A. Add details to the roadmap now so later criteria are fixed in advance:
  1.2.1 and 1.2.4 build the trust-audit scanner and verifier log parsers and
  replay the gate rule table from Rust; 1.2.3 replays the semantic examples as
  `rstest` cases; 2.3.1 replays every grammar corpus entry as a `trybuild` pass
  or fail fixture, with a completeness check. (recommended)

Recommendation rationale: Fixing the replay obligations before those tasks
start prevents their success criteria from being chosen after the fact.

Decision: pending.

ADR: none yet.

## Candidate ADR subjects

- CA1. Numerical and array semantics (technical-design.md §15): recorded in
  ADR-0006; disposition decided by [D07](#d07).
- CA2. Macro staging and stable-Rust application (technical-design.md §15):
  recorded in ADR-0007; disposition decided by [D07](#d07).
- CA3. Backend and cell separation (technical-design.md §15): deferred to task
  1.2.1; disposition decided by [D07](#d07).
- CA4. Initial feature and release scope (technical-design.md §15): recorded in
  ADR-0003; disposition decided by [D07](#d07).
- CA5. Shared semantic kernel (technical-design.md §15): deferred to task 1.2.1
  (B01); disposition decided by [D07](#d07).
- CA6. Public proof compatibility (technical-design.md §15): recorded in
  ADR-0005 and ADR-0009; disposition decided by [D07](#d07).
- CA7. Resource certification (technical-design.md §15): deferred to step 2.4
  (B03); disposition decided by [D07](#d07).
- CA8. Backend input and output control scope (technical-design.md §15):
  deferred to task 1.2.6 (B06); disposition decided by [D07](#d07).

<!-- decisions:end -->
