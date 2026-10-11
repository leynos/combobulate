# Architectural decision record (ADR) 0002: Governance authority and exceptions

## Status

Accepted on 2026-10-10: the sponsor and technical owner, GitHub login `leynos`,
accepts architecture, scope changes, release readiness, trusted-boundary
exceptions, and released proof-API changes; exceptions are short-lived and
never count as proof; no `CODEOWNERS` file is used. Records D01, D02, and D13
in the [decision register](../decision-register.md).

## Date

2026-10-10.

## Context and problem statement

The terms of reference left decision rights open: Q1 asked who accepts
architecture, scope changes, and release readiness, and Q8 asked who accepts
scoped trusted-boundary exceptions and released proof-API changes. Until those
rights were assigned, any later implementation could have had its success
criteria changed after the fact, and an advisory review could have been read as
approval. Technical design GAP5 and GAP9 recorded the same gap.

The project currently has one maintainer. A governance mechanism that assumes
several reviewers would add ceremony without adding control.

## Decision drivers

- An approval must be attributable to a named login and cite the decision it
  accepts; an ambiguous approval accepts nothing.
- Acceptance is not verification: no decision may mark a proof obligation
  discharged, a bet as run, or a capability as eligible.
- Exceptions to the proof-first policy must stay visible, narrow, and
  temporary, so they cannot quietly become permanent trust.
- Controls must suit a single-maintainer repository.

## Options considered

For authority (D01): the sponsor alone, or the sponsor plus a named technical
owner with delegated acceptance of contract records and pre-registrations. For
enforcement (D13): a `.github/CODEOWNERS` file with required code-owner review,
or the base-revision freeze check plus the sponsor's own pull request review
and merge.

## Decision outcome

- Authority (D01). The sponsor and the technical owner are both `leynos`. This
  matches the "Sponsor and technical owner" authority that terms of reference
  §9 already names for Q2 and Q4, so no amendment of that column is needed. The
  implementing agent drafts and recommends; it never accepts.
- Exceptions (D02). An exception is valid from its approval date until its
  `invalid_from` date, at most 90 days and never past the next release-gate
  task (4.3.3 or 6.3.4). Renewal is a new approval. An exception names a
  narrowed claim and can never satisfy a proof-required component; it does not
  waive ordinary safe-API checks.
- Enforcement (D13). No `CODEOWNERS` file. The design checks reject edits to
  accepted records relative to the pull request's merge base, and the sponsor's
  review and merge is the human control. Revisit if another developer joins.
- Approval references. An accepted decision records the accepting login, the
  date, and a structured reference: a session answer quoted verbatim, a pull
  request review, a pull request comment, or a commit. The sponsor's merge of
  the pull request that records an acceptance is its durable confirmation.

## Known risks and limitations

- Session answers are attributed to the sponsor by the Lody session, and pull
  request reviews and merges by GitHub (ExecPlan axiom A4). Neither is verified
  by the design checks.
- Without code-owner review, the freeze check makes an unauthorized edit a
  named failure rather than a blocked merge; the sponsor's review must still
  notice a deliberately weakened check.
- One person holding every role concentrates risk; a second maintainer should
  prompt a review of D01 and D13.
