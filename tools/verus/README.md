# Verus release pin

`VERSION` holds the Verus release, and `SHA256SUMS` holds one `sha256sum` row
that binds that release's archive:

```plaintext
<64 lowercase hex digest>  verus-<VERSION>-x86-linux.zip
```

The archive name is derived from `VERSION`, so a release bump edits both files
together. `make install-verus`, and the shared `install-prover-tools` action in
CI, download the archive named by `VERSION`, verify it against `SHA256SUMS`,
and leave the installation to the pinned `rust-prover-tools` helper. The
archive is stored under `.verus/`, outside Git.

The current pin is Verus `0.2026.09.06.8dea4a2`, its matching Rust `1.98.0`,
and Z3 `4.16.0`. The release archive omits Z3; the same installer provides it.

To change the release, update `VERSION`, record the new archive's digest in
`SHA256SUMS`, run `make verus`, and update every other `verus_release` site
named in `spec/toolchain-profiles.json`. Never infer that another `vstd`
release is compatible from its Cargo version alone.
