//! `cargo tree` parsing and the dependency-prefix predicates VO-1 and VO-3 use.

/// Package-name prefixes that mark a backend dependency.
pub(crate) const BACKEND_PREFIXES: &[&str] = &["glam", "polars"];

/// Package-name prefixes that mark a verifier runtime.
pub(crate) const VERIFIER_PREFIXES: &[&str] = &["kani", "verus", "vstd"];

/// Parses package names from `cargo tree --prefix none` output.
///
/// Each line starts with the package name, then its version, so the first
/// whitespace-separated token is the name whatever follows it.
pub(crate) fn package_names(tree: &str) -> Vec<String> {
    tree.lines()
        .filter_map(|line| line.split_whitespace().next())
        .filter(|name| !name.is_empty())
        .map(str::to_owned)
        .collect()
}

/// Reports whether the tree contains the package with exactly this name.
pub(crate) fn contains_package(tree: &str, name: &str) -> bool {
    package_names(tree).iter().any(|package| package == name)
}

/// Reports the packages in the tree whose names start with a prefix.
pub(crate) fn packages_with_prefix(tree: &str, prefixes: &[&str]) -> Vec<String> {
    package_names(tree)
        .into_iter()
        .filter(|name| prefixes.iter().any(|prefix| name.starts_with(prefix)))
        .collect()
}

/// Reports backend packages that reached the tree.
pub(crate) fn backend_packages(tree: &str) -> Vec<String> {
    packages_with_prefix(tree, BACKEND_PREFIXES)
}

/// Reports verifier packages that reached the tree.
pub(crate) fn verifier_packages(tree: &str) -> Vec<String> {
    packages_with_prefix(tree, VERIFIER_PREFIXES)
}

/// Reports the features `cargo tree -e features` resolved for one package.
///
/// `-e all` renders each enabled feature as its own `name feature "feature"`
/// line, so this reads what Cargo actually selected rather than what the
/// manifest asked for: a default feature that came back through another
/// dependency appears here and nowhere in the requirement.
pub(crate) fn features_of(tree: &str, package: &str) -> Vec<String> {
    tree.lines()
        .filter_map(|line| resolved_feature(line, package))
        .collect()
}

/// Extracts one feature edge, requiring the exact package name.
///
/// The prefix is matched on the whole name followed by ` feature "`, so
/// `polars-buffer feature "…"` cannot be read as a feature of `polars`.
fn resolved_feature(line: &str, package: &str) -> Option<String> {
    let rest = line.strip_prefix(package)?.strip_prefix(" feature \"")?;
    Some(rest.strip_suffix('"')?.to_owned())
}
