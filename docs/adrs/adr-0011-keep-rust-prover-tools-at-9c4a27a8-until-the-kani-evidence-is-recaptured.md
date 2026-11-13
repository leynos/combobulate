# Architectural decision record (ADR) 0011: Keep rust-prover-tools at 9c4a27a8 until the Kani evidence is recaptured

## Status

Accepted on 2026-11-13 as a recorded exception to the estate's prover-tooling
standard (Concordat rule `rust-prover-tooling`, checks PT-001 and PT-002).

## Date

2026-11-13.

## Context and problem statement

The estate standard asks a repository that uses Kani or Verus to pin
`rust-prover-tools` to one agreed commit, and to install provers in continuous
integration only through the shared `install-prover-tools` action. This
repository pins `rust-prover-tools` at
`9c4a27a86c678ceac1155404f45d95ee4a14a172` in `tools/rust-prover-tools/REF`,
and its `formal.yml` and `profile-measurements.yml` workflows install Kani
themselves.

The Kani provenance records (for example
`scripts/tests/fixtures/kani_logs/provenance.json`, field `prover_tools_ref`)
name `9c4a27a8` as the revision that captured their observations. A different
revision would install a different Kani route, and the recorded observations
would no longer describe the tool that produced them.

## Decision outcome

Keep the pin at `9c4a27a8` and keep the workflows' own Kani installation until
the Kani evidence is recaptured. The exception is declared as data in
`.concordat` and waives PT-001 and PT-002 only; it holds while the repository's
pin is still `9c4a27a8` and while this record exists.

## Review trigger

Revisit when the Kani evidence is recaptured under a newer `rust-prover-tools`
revision. At that point move the pin to the estate's agreed commit, move the
workflows onto `install-prover-tools`, and delete the exception.
