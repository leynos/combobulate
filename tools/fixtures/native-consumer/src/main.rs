//! An ordinary downstream consumer of the native-only profile.
//!
//! The binary exists so `tests/native_consumer_e2e.rs` can prove the facade is
//! usable from outside the workspace with default features disabled: it takes
//! the facade by path, reads the build profile, and prints one line. Nothing
//! in its dependency graph may be a backend or a verifier.

use combobulate::BuildProfile;

fn main() {
    println!("{}", BuildProfile::current());
}
