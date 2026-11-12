# Verus release pin

`VERSION` holds the Verus release, and `SHA256SUMS` holds one `sha256sum` row
that binds that release's archive:

```text
<64 lowercase hex digest>  verus-<VERSION>-x86-linux.zip
```

The archive name is derived from `VERSION`, so a release bump edits both files
together. `prover_release_pins_are_complete` in
`tests/prover_tools_contract.rs` checks that relationship, not a copied value,
so a legitimate bump does not also edit the test. `make install-verus`
downloads the archive named by `VERSION`, verifies it against `SHA256SUMS`, and
delegates installation to the commit-pinned `rust-prover-tools` helper. The
archive is stored under `.verus/`, outside Git.

The current pin is Verus `0.2026.09.06.8dea4a2`, its matching Rust `1.98.0`,
and Z3 `4.16.0`. The release archive omits Z3; the probes obtain that solver
through `z3-solver==4.16.0.0`.

A release change requires a sponsor-approved acceptance-control amendment.
Update `VERSION`, record the new archive's digest in `SHA256SUMS`, rerun the
wiring probes, and update the profile record, probe provenance, and every other
`verus_release` site named in `spec/toolchain-profiles.json`. Never infer that
another `vstd` release is compatible from its Cargo version alone.
