//! `cargo tree` parsing and the dependency-prefix predicates VO-1 and VO-3 use.

/// Package-name prefixes that mark a backend dependency.
pub(super) const BACKEND_PREFIXES: &[&str] = &["glam", "polars"];

/// Package-name prefixes that mark a verifier runtime.
pub(super) const VERIFIER_PREFIXES: &[&str] = &["kani", "verus", "vstd"];

/// Parses package names from `cargo tree --prefix none` output.
///
/// Each line starts with the package name, then its version, so the first
/// whitespace-separated token is the name whatever follows it.
pub(super) fn package_names(tree: &str) -> Vec<String> {
    tree.lines()
        .filter_map(|line| line.split_whitespace().next())
        .filter(|name| !name.is_empty())
        .map(str::to_owned)
        .collect()
}

/// Reports whether the tree contains the package with exactly this name.
pub(super) fn contains_package(tree: &str, name: &str) -> bool {
    package_names(tree).iter().any(|package| package == name)
}

/// Reports the packages in the tree whose names start with a prefix.
pub(super) fn packages_with_prefix(tree: &str, prefixes: &[&str]) -> Vec<String> {
    package_names(tree)
        .into_iter()
        .filter(|name| prefixes.iter().any(|prefix| name.starts_with(prefix)))
        .collect()
}

/// Reports backend packages that reached the tree.
pub(super) fn backend_packages(tree: &str) -> Vec<String> {
    packages_with_prefix(tree, BACKEND_PREFIXES)
}

/// Reports verifier packages that reached the tree.
pub(super) fn verifier_packages(tree: &str) -> Vec<String> {
    packages_with_prefix(tree, VERIFIER_PREFIXES)
}
