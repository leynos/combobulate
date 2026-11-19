//! Source checks that keep the kernel `#![no_std]` and allocation-free.
//!
//! The kernel contract is about attributes the compiler acts on. A doc comment
//! or a string literal that merely names `#![no_std]` does not put the crate in
//! `no_std` mode, so every check runs over code with comments and literals
//! removed. Without that step the crate's own documentation would satisfy the
//! check after a contributor deleted the real attribute.
//!
//! Two scopes share one scan. The crate attributes — `#![no_std]` and the two
//! denials — belong to `lib.rs` alone, and a submodule that restated them would
//! not make the crate any stricter. The rules that keep one executable body
//! belong to every kernel source file, because a substitute definition is just
//! as wrong in a submodule as in the root, and a root-only scan cannot see it.
//! The seeded tree under `tests/fixtures/kernel-source/` is read by the same
//! functions, so a scan that stopped reading submodules fails its own test
//! rather than passing vacuously.
//!
//! The lexical scanner that removes comments and literals lives in
//! [`scanner`], and the attribute reader that classifies what the rules are
//! stated over lives in [`attributes`]. Each is a child module so its own tests
//! can sit beside it, and so this file stays under the repository's length
//! limit.

use std::{error::Error, io};

use cap_std::{ambient_authority, fs_utf8::Dir};

#[path = "workspace_attributes.rs"]
mod attributes;
#[path = "workspace_scanner.rs"]
mod scanner;

use attributes::{
    Attribute,
    LintLevel,
    Scope,
    attributes as scan_attributes,
    final_lint_level,
    lint_list,
    split_attribute,
};
use scanner::strip_comments_and_literals;

/// The file name that alone carries the crate attributes.
const CRATE_ROOT: &str = "lib.rs";

/// The kernel crate root, which the crate-attribute checks read.
const KERNEL_ROOT: &str = "crates/combobulate-kernel/src/lib.rs";

/// The lints the kernel denies, which no kernel file may allow or warn.
const CORE_LINTS: [&str; 2] = [
    "clippy::std_instead_of_core",
    "clippy::alloc_instead_of_core",
];

/// The lint levels no kernel file may set for a core lint.
const FORBIDDEN_LEVELS: [&str; 3] = ["allow", "warn", "expect"];

/// One Rust source file read from a kernel-shaped tree.
pub(super) struct KernelFile {
    /// The file's path, relative to the directory the walk started at.
    pub(super) path: String,
    /// The file's own text.
    pub(super) source: String,
}

/// Reads the kernel crate root from the workspace.
pub(super) fn kernel_source() -> Result<String, Box<dyn Error>> {
    let directory = Dir::open_ambient_dir(env!("CARGO_MANIFEST_DIR"), ambient_authority())?;
    Ok(directory.read_to_string(KERNEL_ROOT)?)
}

/// Reads every Rust source file beneath a repository-relative directory.
///
/// The walk is recursive because the kernel keeps its operations in one file
/// each, and a rule that only reached the first directory would be defeated by
/// creating a subdirectory. The paths are relative to `directory`, so the same
/// function reads the live kernel and a seeded fixture tree.
///
/// ```text
/// sources_under("crates/combobulate-kernel/src")
/// // [lib.rs, elementwise_add.rs, ...], sorted by path
/// ```
pub(super) fn sources_under(directory: &str) -> Result<Vec<KernelFile>, Box<dyn Error>> {
    let root = Dir::open_ambient_dir(env!("CARGO_MANIFEST_DIR"), ambient_authority())?;
    let mut files = Vec::new();
    collect(&root.open_dir(directory)?, "", &mut files)?;
    files.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(files)
}

/// Reads every Rust source file beneath one open directory.
///
/// The extension check is case-insensitive, as the compiler's own file lookup
/// is on a case-insensitive filesystem, so a file named `Lib.RS` cannot slip
/// past the rules by its spelling.
fn collect(directory: &Dir, prefix: &str, files: &mut Vec<KernelFile>) -> io::Result<()> {
    for listing in directory.read_dir(".")? {
        let entry = listing?;
        let name = entry.file_name()?;
        let path = join_path(prefix, &name);
        // A subdirectory is descended into rather than inspected: the rules are
        // about files, and a directory that shares the kernel's shape must be
        // walked just as the root is.
        if entry.file_type()?.is_dir() {
            collect(&directory.open_dir(&name)?, &path, files)?;
        } else {
            push_if_rust(directory, &name, path, files)?;
        }
    }
    Ok(())
}

/// Returns the repository-relative path of an entry named `name`.
///
/// The walk's first level has no prefix, so an empty one must not produce a
/// leading separator: `lib.rs`, not `/lib.rs`.
fn join_path(prefix: &str, name: &str) -> String {
    if prefix.is_empty() {
        name.to_owned()
    } else {
        format!("{prefix}/{name}")
    }
}

/// Reads `name` into `files` when Rust would compile it, and ignores it
/// otherwise.
fn push_if_rust(
    directory: &Dir,
    name: &str,
    path: String,
    files: &mut Vec<KernelFile>,
) -> io::Result<()> {
    if has_rust_extension(name) {
        files.push(KernelFile {
            source: directory.read_to_string(name)?,
            path,
        });
    }
    Ok(())
}

/// Reports whether `name` carries the extension Rust compiles.
fn has_rust_extension(name: &str) -> bool {
    name.rsplit_once('.')
        .is_some_and(|(_, extension)| extension.eq_ignore_ascii_case("rs"))
}

/// Reports every rule the files of a kernel-shaped tree break.
///
/// A tree with no `lib.rs` is reported rather than accepted: the crate
/// attributes would otherwise go unchecked, which is the vacuous pass this
/// check exists to rule out.
///
/// ```text
/// kernel_tree_violations(&[KernelFile { path: "mod.rs", .. }])
/// // ["the kernel tree must contain its lib.rs crate root"]
/// ```
pub(super) fn kernel_tree_violations(files: &[KernelFile]) -> Vec<String> {
    let mut violations = Vec::new();
    if !files.iter().any(|file| file.path == CRATE_ROOT) {
        violations.push(format!(
            "the kernel tree must contain its {CRATE_ROOT} crate root"
        ));
    }
    for file in files {
        violations.extend(file_violations(file));
    }
    violations
}

/// Reports the rules one kernel file breaks, naming the file.
fn file_violations(file: &KernelFile) -> Vec<String> {
    item_violations(&code_only(&file.source), file.path == CRATE_ROOT)
        .into_iter()
        .map(|message| format!("{}: {message}", file.path))
        .collect()
}

/// Reports the `no_std`, allocation, and lint rules the kernel source lacks.
///
/// Checks run over code only, so a comment or string that names an attribute
/// cannot stand in for the attribute itself.
///
/// ```text
/// kernel_source_violations("#![no_std]\n")
/// // reports the two missing lint rules
/// kernel_source_violations("// #![no_std]\n")
/// // reports the missing attribute as well
/// ```
pub(super) fn kernel_source_violations(source: &str) -> Vec<String> {
    item_violations(&code_only(source), true)
}

/// Reports the rules one kernel file's code breaks.
///
/// The crate-attribute rules are stated over the file name, so a root-only
/// check cannot be smuggled onto a submodule by copying the attributes there.
fn item_violations(code: &str, is_root: bool) -> Vec<String> {
    let mut violations = if is_root {
        crate_rule_violations(code)
    } else {
        Vec::new()
    };
    for text in ["extern crate alloc", "extern crate std"] {
        if code.contains(text) {
            violations.push(format!("must not contain {text}"));
        }
    }
    if code.contains("cfg(not(verus_keep_ghost))") {
        violations.push("must not contain cfg(not(verus_keep_ghost))".to_owned());
    }
    for attribute in scan_attributes(code, Scope::All) {
        violations.extend(attribute_violations(code, &attribute));
    }
    violations
}

/// Reports the crate attributes a kernel root must declare.
fn crate_rule_violations(code: &str) -> Vec<String> {
    let mut violations = Vec::new();
    if !code.contains("#![no_std]") {
        violations.push("the kernel crate root must declare #![no_std]".to_owned());
    }
    for lint in CORE_LINTS {
        if !matches!(
            final_lint_level(code, lint),
            Some(LintLevel::Deny | LintLevel::Forbid)
        ) {
            violations.push(format!("the kernel crate root must deny {lint}"));
        }
    }
    violations
}

/// Reports the rules one attribute breaks in a kernel file.
fn attribute_violations(code: &str, attribute: &Attribute<'_>) -> Vec<String> {
    let mut violations = lint_level_violations(attribute.body);
    let normal = attribute.normalised();
    if substitutes_a_function(code, attribute) {
        violations.push(format!("must not put {normal} on a fn item"));
    }
    violations
}

/// Reports whether an attribute hides a substitute body for a function.
///
/// Only an outer `cfg(verus_keep_ghost)` or `cfg(kani)` does: an inner one
/// gates the whole module's contents, which the ADR-0010 pattern needs, and
/// `cfg_attr` is how the contract attributes reach the shipped body. The item
/// after the attribute must be a function, because gating a `use` or a
/// constant replaces no executable body.
fn substitutes_a_function(code: &str, attribute: &Attribute<'_>) -> bool {
    let normal = attribute.normalised();
    let is_substitute_gate = matches!(normal.as_str(), "cfg(verus_keep_ghost)" | "cfg(kani)");
    is_substitute_gate && !attribute.is_inner && attributes::gates_a_function(code, attribute.end)
}

/// Reports a core lint this attribute allows, warns about, or expects.
fn lint_level_violations(body: &str) -> Vec<String> {
    let Some((level, list)) = lint_setting(body) else {
        return Vec::new();
    };
    CORE_LINTS
        .iter()
        .filter(|lint| lint_list(list).any(|item| item == **lint))
        .map(|lint| format!("must not {level} {lint}"))
        .collect()
}

/// Returns the attribute's lint level and list when it sets one.
///
/// `expect` is included even though no crate-level `expect` can weaken a
/// `deny`: a file that expected one of these lints would still be the place
/// where core-only code stopped being enforced.
fn lint_setting(body: &str) -> Option<(&str, &str)> {
    let (name, list) = split_attribute(body)?;
    FORBIDDEN_LEVELS.contains(&name).then_some((name, list))
}

/// Returns `source` with comments and string literals removed.
///
/// Whitespace is collapsed so `extern /* note */ crate alloc` still reads as
/// the declaration a violation check must see.
fn code_only(source: &str) -> String {
    strip_comments_and_literals(source)
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}
