# User guide

Combobulate's array algebra is not yet implemented. The current crate provides
only a disposable `greet()` stub for scaffold checks; it carries no stability
promise. Do not use the proposed design examples as working Rust examples.

Read the [language reference](language-reference.md) for the intended `comb!`
pipeline notation, verbs, modifiers, and conjunctions. The
[technical design](technical-design.md) specifies shape errors, execution
boundaries, cost admission, and verification contracts. The
[roadmap](roadmap.md) records the experiments required before those proposals
become supported functionality.

For building and checking the current source, follow the
[developer guide](developers-guide.md).

## Project status, licence, and stability

Combobulate is ISC-licensed. It is not published to crates.io: publication
waits until the Core acceptance dossier (roadmap task 4.3.3) passes and the
sponsor approves release
([ADR-0004](adrs/adr-0004-licence-and-publication.md)). Until then, use it
from the Git repository only.

Before version 1.0, any release may change the API without compatibility shims,
following Cargo's rule that a change to the leftmost non-zero version component
is breaking. The public proof interface (logical models, pre- and
postconditions, lemmas, and trust declarations) is versioned with the crate: a
strengthened precondition or weakened postcondition is a breaking change even
when no Rust signature changes
([ADR-0005](adrs/adr-0005-pre-1-0-api-and-proof-interface-policy.md)). The
[evidence gate](adrs/adr-0009-proof-first-policy-and-evidence-gate.md) decides
what evidence backs each published proof claim. A schema-valid record reaches
`proof` only when it is deductive evidence or bounded evidence with
`type-complete` bounds, has a `verified` outcome, and its verdict is parsed
from a committed log with a digest. It must include at least one success
witness and every witness must be reached; it must include at least one
negative control, every required control must be rejected as intended, and no
control may be accepted or rejected for another reason. Every trusted item must
name a declared assumption or cited exception. The binding must match the
registered executable and specification digests, source revision, target,
features, semantic policy, backend profile, and implementation relation; the
run must use `full-profile`, and no exception may apply. Partial-bounds
evidence remains `bounded`, never `proof`. The initial release covers the Core
scope class of the [language reference](language-reference.md)
([ADR-0003](adrs/adr-0003-initial-release-scope.md)).

## Check proof-evidence records

Run
`uv run scripts/check_evidence.py --as-of YYYY-MM-DD [--require
proof|bounded|tested] spec/evidence/record.json`
to check one or more records. The date is required and makes exception
evaluation reproducible. The minimum level defaults to `tested`; `proof`,
`bounded`, and `tested` are the supported requirements. The command exits `0`
when every record meets the requirement, `1` when a record is admitted below
it, and `2` for unreadable input, a schema failure, or a usage error. A
verifier's verdict remains self-reported until a registered adapter validates
the cited log digest and supplies a matching result; registration by itself
cannot satisfy `proof` or `bounded`.

Records use schema version 2. Version 1 records are rejected; see the
[evidence-record migration notes](revision-0.2.md#evidence-record-schema-migration)
and the [producer reference](evidence-and-decision-records.md) before updating
a producer.
