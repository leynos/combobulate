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

use camino::{Utf8Path, Utf8PathBuf};
use cap_std::{ambient_authority, fs_utf8::Dir};

#[path = "workspace_attributes.rs"]
mod attributes;
#[cfg(test)]
#[path = "workspace_attributes_tests.rs"]
mod attributes_tests;
#[path = "workspace_scanner.rs"]
mod scanner;

use attributes::{
    Attribute,
    LintLevel,
    Scope,
    Split,
    attributes as scan_attributes,
    final_lint_level,
};
use scanner::{Code, strip_comments_and_literals};

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
    ///
    /// A `Utf8PathBuf` rather than a `String` because the value is joined,
    /// compared against a file name, and printed as a path; an arbitrary
    /// string would let a caller pass something no walk could produce.
    pub(super) path: Utf8PathBuf,
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
pub(super) fn sources_under(directory: &Utf8Path) -> Result<Vec<KernelFile>, Box<dyn Error>> {
    let root = Dir::open_ambient_dir(env!("CARGO_MANIFEST_DIR"), ambient_authority())?;
    let mut files = Vec::new();
    collect(&root.open_dir(directory)?, Utf8Path::new(""), &mut files)?;
    files.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(files)
}

/// Reads every Rust source file beneath one open directory.
///
/// The extension check is case-insensitive, as the compiler's own file lookup
/// is on a case-insensitive filesystem, so a file named `Lib.RS` cannot slip
/// past the rules by its spelling.
fn collect(directory: &Dir, prefix: &Utf8Path, files: &mut Vec<KernelFile>) -> io::Result<()> {
    for listing in directory.read_dir(".")? {
        let entry = listing?;
        let name = entry.file_name()?;
        let path = prefix.join(&name);
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

/// Reads `name` into `files` when Rust would compile it, and ignores it
/// otherwise.
fn push_if_rust(
    directory: &Dir,
    name: &str,
    path: Utf8PathBuf,
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
    if !files
        .iter()
        .any(|file| file.path == Utf8Path::new(CRATE_ROOT))
    {
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
    item_violations(
        &code_only(&file.source),
        file.path == Utf8Path::new(CRATE_ROOT),
    )
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
fn item_violations(code: &Code, is_root: bool) -> Vec<String> {
    let text = code.text();
    let mut violations = if is_root {
        crate_rule_violations(code)
    } else {
        Vec::new()
    };
    for declaration in ["extern crate alloc", "extern crate std"] {
        if text.contains(declaration) {
            violations.push(format!("must not contain {declaration}"));
        }
    }
    // Compared without whitespace, because `cfg( not(verus_keep_ghost) )` is
    // the same gate to a compiler and a literal match would let it through.
    if text
        .chars()
        .filter(|character| !character.is_whitespace())
        .collect::<String>()
        .contains("cfg(not(verus_keep_ghost))")
    {
        violations.push("must not contain cfg(not(verus_keep_ghost))".to_owned());
    }
    for attribute in scan_attributes(code, Scope::All) {
        violations.extend(attribute_violations(code, &attribute));
    }
    violations
}

/// Reports the crate attributes a kernel root must declare.
fn crate_rule_violations(code: &Code) -> Vec<String> {
    let mut violations = Vec::new();
    if !code.text().contains("#![no_std]") {
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
fn attribute_violations(code: &Code, attribute: &Attribute<'_>) -> Vec<String> {
    let mut violations = lint_level_violations(attribute);
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
fn substitutes_a_function(code: &Code, attribute: &Attribute<'_>) -> bool {
    let normal = attribute.normalised();
    let is_substitute_gate = matches!(normal.as_str(), "cfg(verus_keep_ghost)" | "cfg(kani)");
    is_substitute_gate && !attribute.is_inner && attributes::gates_a_function(code, attribute.end)
}

/// Reports a core lint this attribute allows, warns about, or expects.
fn lint_level_violations(attribute: &Attribute<'_>) -> Vec<String> {
    let Some(split) = lint_setting(attribute) else {
        return Vec::new();
    };
    CORE_LINTS
        .iter()
        .filter(|lint| split.lints().any(|item| item == **lint))
        .map(|lint| format!("must not {} {lint}", split.name))
        .collect()
}

/// Returns the attribute's lint level and list when it sets one.
///
/// `expect` is included even though no crate-level `expect` can weaken a
/// `deny`: a file that expected one of these lints would still be the place
/// where core-only code stopped being enforced.
///
/// A `cfg_attr` is unwrapped to the attribute it applies conditionally, so
/// `#[cfg_attr(not(verus_keep_ghost), allow(clippy::std_instead_of_core))]`
/// is read as the `allow` it is. The condition is not evaluated: a kernel
/// file may not carry a conditional allowance at all, because whether it
/// applies depends on a build the boundary cannot see.
fn lint_setting<'a>(attribute: &Attribute<'a>) -> Option<Split<'a>> {
    let split = attribute.split()?;
    if split.name == "cfg_attr" {
        return conditional_setting(attribute, split.list);
    }
    FORBIDDEN_LEVELS.contains(&split.name).then_some(split)
}

/// Returns the lint setting a `cfg_attr` applies, if any.
///
/// The payload follows the predicate, and the payload itself may hold several
/// attributes. Splitting on the first comma would cut inside a predicate such
/// as `any(unix, windows)`, so the top-level commas are found by depth and
/// every payload after the predicate is examined.
fn conditional_setting<'a>(attribute: &Attribute<'a>, list: &'a str) -> Option<Split<'a>> {
    payloads(list).find_map(|payload| {
        let unwrapped = Attribute {
            body: payload,
            end: attribute.end,
            is_inner: attribute.is_inner,
        };
        lint_setting(&unwrapped)
    })
}

/// Yields the `cfg_attr` payloads after its predicate, split at depth zero.
///
/// `#[cfg_attr(predicate, attribute, attribute)]` carries one predicate and
/// one or more payloads. A comma inside parentheses or brackets belongs to
/// whichever of them encloses it, so only commas seen at depth zero separate
/// the parts. The first part is the predicate and is skipped.
fn payloads(list: &str) -> impl Iterator<Item = &str> + '_ {
    let mut depth = 0_usize;
    let mut start = 0_usize;
    let mut parts: Vec<&str> = Vec::new();
    for (position, character) in list.char_indices() {
        match character {
            '(' | '[' | '{' => depth += 1,
            ')' | ']' | '}' => depth = depth.saturating_sub(1),
            ',' if depth == 0 => {
                parts.push(list.get(start..position).unwrap_or_default());
                start = position + 1;
            }
            _ => {}
        }
    }
    parts.push(list.get(start..).unwrap_or_default());
    parts.into_iter().skip(1).map(str::trim)
}

/// Returns `source` with comments and string literals removed, as [`Code`].
///
/// Whitespace is collapsed so `extern /* note */ crate alloc` still reads as
/// the declaration a violation check must see. Collapsing happens here rather
/// than in the scanner because it is about how these rules read the text, not
/// about what a comment or literal is.
fn code_only(source: &str) -> Code {
    let collapsed = strip_comments_and_literals(source)
        .text()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    Code::stripped(collapsed)
}
