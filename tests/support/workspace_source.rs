//! Source checks that keep the kernel `#![no_std]` and allocation-free.

use std::error::Error;

use cap_std::{ambient_authority, fs_utf8::Dir};

/// Reads the kernel crate root from the workspace.
pub(super) fn kernel_source() -> Result<String, Box<dyn Error>> {
    let directory = Dir::open_ambient_dir(env!("CARGO_MANIFEST_DIR"), ambient_authority())?;
    Ok(directory.read_to_string("crates/combobulate-kernel/src/lib.rs")?)
}

/// Reports the `no_std`, allocation, and lint rules the kernel source lacks.
///
/// Comments could satisfy a `contains` check without the attribute being
/// effective, but a planted comment is not a plausible defect; a removed or
/// renamed attribute is, and that fails here.
pub(super) fn kernel_source_violations(source: &str) -> Vec<String> {
    let mut violations = Vec::new();
    for (text, description) in [
        ("#![no_std]", "declare #![no_std]"),
        (
            "clippy::std_instead_of_core",
            "deny clippy::std_instead_of_core",
        ),
        (
            "clippy::alloc_instead_of_core",
            "deny clippy::alloc_instead_of_core",
        ),
    ] {
        if !source.contains(text) {
            violations.push(format!("the kernel crate root must {description}"));
        }
    }
    for text in ["extern crate alloc", "extern crate std"] {
        if source.contains(text) {
            violations.push(format!("the kernel crate root must not contain {text}"));
        }
    }
    violations
}
