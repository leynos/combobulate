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
what evidence backs each published proof claim: a claim is `proof` only when a
verifier's verdict is parsed from its log, every success witness is reached,
every negative control fails for the intended reason, and every trusted
assumption is declared; bounded model-checking evidence over partial bounds is
reported as `bounded`, never `proof`. The initial release covers the Core scope
class of the [language reference](language-reference.md)
([ADR-0003](adrs/adr-0003-initial-release-scope.md)).
