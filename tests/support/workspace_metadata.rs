//! Dependency-direction predicates over `cargo metadata --no-deps` output.

use serde::Deserialize;

use super::tree::BACKEND_PREFIXES;

/// The facade package that ships to consumers.
pub(crate) const FACADE: &str = "combobulate";

/// The `#![no_std]` kernel package.
pub(crate) const KERNEL: &str = "combobulate-kernel";

/// The procedural-macro package.
pub(crate) const MACROS: &str = "combobulate-macros";

/// Every member package declared by the workspace root.
pub(crate) const MEMBERS: &[&str] = &[FACADE, KERNEL, MACROS];

/// A package declared by `cargo metadata --no-deps`.
#[derive(Debug, Deserialize)]
pub(crate) struct Package {
    /// Cargo package name.
    pub(crate) name: String,
    /// Build targets, used to recognize procedural-macro crates.
    #[serde(default)]
    pub(crate) targets: Vec<Target>,
    /// Declared dependencies of every kind and target.
    #[serde(default)]
    pub(crate) dependencies: Vec<Dependency>,
}

/// A build target declared by a package.
#[derive(Debug, Deserialize)]
pub(crate) struct Target {
    /// Cargo target kinds such as `lib` or `proc-macro`.
    #[serde(default)]
    pub(crate) kind: Vec<String>,
}

/// A declared dependency edge.
#[derive(Debug, Deserialize)]
pub(crate) struct Dependency {
    /// Dependency package name.
    pub(crate) name: String,
    /// Cargo kind: absent for normal, otherwise `dev` or `build`.
    #[serde(default)]
    pub(crate) kind: Option<String>,
}

/// The `packages` projection of `cargo metadata --no-deps`.
#[derive(Debug, Deserialize)]
pub(crate) struct Metadata {
    /// Every workspace member and path dependency.
    pub(crate) packages: Vec<Package>,
}

/// Parses `cargo metadata --no-deps` output.
pub(crate) fn parse_metadata(text: &str) -> Result<Metadata, serde_json::Error> {
    serde_json::from_str(text)
}

/// Finds one declared package by name.
pub(crate) fn package<'a>(metadata: &'a Metadata, name: &str) -> Option<&'a Package> {
    metadata
        .packages
        .iter()
        .find(|package| package.name == name)
}

/// Returns every declared package name in order.
pub(crate) fn package_names(metadata: &Metadata) -> Vec<String> {
    metadata
        .packages
        .iter()
        .map(|package| package.name.clone())
        .collect()
}

/// Returns the dependency names the kernel declares, of every kind and target.
///
/// A target-specific or backend edge still appears here, so an empty result is
/// the kernel-isolation claim VO-1 asks for.
pub(crate) fn kernel_dependency_names(metadata: &Metadata) -> Vec<String> {
    package(metadata, KERNEL)
        .into_iter()
        .flat_map(|kernel| {
            kernel
                .dependencies
                .iter()
                .map(|dependency| dependency.name.clone())
        })
        .collect()
}

/// Reports backend dependencies the kernel declares.
pub(crate) fn kernel_backend_dependencies(metadata: &Metadata) -> Vec<String> {
    kernel_dependency_names(metadata)
        .into_iter()
        .filter(|name| {
            BACKEND_PREFIXES
                .iter()
                .any(|prefix| name.starts_with(prefix))
        })
        .collect()
}

/// Reports every dependency-direction violation in the declared graph.
///
/// The graph is shallow: `--no-deps` still lists each package's declared edges
/// of every kind and target, which is exactly what VO-2 constrains. A
/// dev-dependency cycle back to the facade is deliberately permitted.
pub(crate) fn direction_violations(metadata: &Metadata) -> Vec<String> {
    let mut violations = Vec::new();
    for package in &metadata.packages {
        for dependency in &package.dependencies {
            if let Some(violation) = direction_violation(package, dependency) {
                violations.push(violation);
            }
        }
    }
    violations
}

/// Reports whether the facade declares a normal dependency on `name`.
pub(crate) fn facade_depends_normally_on(metadata: &Metadata, name: &str) -> bool {
    package(metadata, FACADE).is_some_and(|facade| {
        facade
            .dependencies
            .iter()
            .any(|dependency| dependency.name == name && dependency.kind.is_none())
    })
}

/// Classifies one declared edge, returning a message when it breaks a rule.
///
/// Each rule is a named predicate so no single condition carries more than one
/// branch. The first matching rule names the edge that violates it.
fn direction_violation(package: &Package, dependency: &Dependency) -> Option<String> {
    if is_member_to_facade_edge(package, dependency) {
        return Some(format!(
            "{} must not have a {} dependency on {FACADE}",
            package.name,
            dependency.kind.as_deref().unwrap_or("normal")
        ));
    }
    if is_forbidden_macros_edge(package, dependency) {
        return Some(format!("{MACROS} must not depend on {}", dependency.name));
    }
    if is_kernel_to_member_edge(package, dependency) {
        return Some(format!(
            "{KERNEL} must not depend on member {}",
            dependency.name
        ));
    }
    if is_build_edge_to_kernel(dependency) {
        return Some(format!(
            "{} must not build-depend on {KERNEL}",
            package.name
        ));
    }
    if is_macro_edge_to_kernel(package, dependency) {
        return Some(format!(
            "procedural-macro crate {} must not depend on {KERNEL}",
            package.name
        ));
    }
    None
}

/// Reports a member edge back to the facade that would create a release cycle.
fn is_member_to_facade_edge(package: &Package, dependency: &Dependency) -> bool {
    is_member(package) && is_facade_target(dependency) && is_normal_or_build(dependency)
}

/// Reports whether the edge names the facade package.
fn is_facade_target(dependency: &Dependency) -> bool { dependency.name == FACADE }

/// Reports whether the edge is a normal or build dependency rather than a dev one.
fn is_normal_or_build(dependency: &Dependency) -> bool {
    matches!(dependency.kind.as_deref(), None | Some("build"))
}

/// Reports a macro-crate edge to the kernel or to a backend.
fn is_forbidden_macros_edge(package: &Package, dependency: &Dependency) -> bool {
    package.name == MACROS && is_forbidden_macros_target(&dependency.name)
}

/// Reports a package the macro crate must never depend on.
fn is_forbidden_macros_target(name: &str) -> bool { name == KERNEL || is_backend(name) }

/// Reports a kernel edge to another workspace member.
fn is_kernel_to_member_edge(package: &Package, dependency: &Dependency) -> bool {
    package.name == KERNEL && is_member_name(&dependency.name)
}

/// Reports a build-dependency edge to the kernel, which would run host code.
fn is_build_edge_to_kernel(dependency: &Dependency) -> bool {
    dependency.name == KERNEL && dependency.kind.as_deref() == Some("build")
}

/// Reports a procedural-macro edge to the kernel.
fn is_macro_edge_to_kernel(package: &Package, dependency: &Dependency) -> bool {
    dependency.name == KERNEL && is_procedural_macro(package)
}

/// Reports whether the package is one of the three workspace members.
fn is_member(package: &Package) -> bool { is_member_name(&package.name) }

/// Reports whether `name` names a workspace member.
fn is_member_name(name: &str) -> bool { MEMBERS.contains(&name) }

/// Reports whether the name marks a backend dependency.
fn is_backend(name: &str) -> bool {
    BACKEND_PREFIXES
        .iter()
        .any(|prefix| name.starts_with(prefix))
}

/// Reports whether the package builds a procedural macro.
fn is_procedural_macro(package: &Package) -> bool {
    package
        .targets
        .iter()
        .any(|target| target.kind.iter().any(|kind| kind == "proc-macro"))
}
