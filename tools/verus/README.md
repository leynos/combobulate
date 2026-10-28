# Verus release pin

The capability probes use Verus `0.2026.09.06.8dea4a2`, its matching Rust
`1.98.0`, and Z3 `4.16.0`. Its checksum-verified release archive omits Z3; the
probes obtain that solver through `z3-solver==4.16.0.0`. `make install-verus`
delegates installation to the commit-pinned `rust-prover-tools` helper. The
archive is stored under `.verus/`, outside Git.

A release change requires a sponsor-approved acceptance-control amendment.
Update `VERSION` and the archive digest in `SHA256SUMS` together, rerun the
wiring probes, and update the profile record and probe provenance. Never infer
that another `vstd` release is compatible from its Cargo version alone.
