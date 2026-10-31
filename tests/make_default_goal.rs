//! Proves that a bare Make invocation builds instead of installing a verifier.

use std::process::Command;

/// A bare `make` must build the library, not run the first declared target.
///
/// The prover targets are declared above `build` for readability, so Make would
/// otherwise adopt `install-kani` as its default goal and a developer running a
/// plain `make` would install a verifier instead of compiling the crate.
#[test]
fn bare_make_builds_the_library() {
    let output = Command::new("make")
        .args(["-n", "-B", "--no-print-directory"])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .env("CARGO", "probe-cargo")
        .env("CHECK_BUILD_TOOLS", "probe-check")
        .output()
        .expect("start a dry-run of the default Make goal");

    assert!(
        output.status.success(),
        "the default goal must parse: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let printed = String::from_utf8_lossy(&output.stdout);
    assert!(
        printed.contains("probe-cargo build"),
        "a bare make must invoke the Cargo build: {printed}"
    );
    assert!(
        !printed.contains("kani install"),
        "a bare make must not install the pinned Kani release: {printed}"
    );
}
