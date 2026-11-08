//! Contracts for the hosted coverage backend and Act's development defaults.

use serde_yaml::Value;

const CI: &str = include_str!("../.github/workflows/ci.yml");
const MAIN: &str = include_str!("../.github/workflows/coverage-main.yml");
const ACT: &str = include_str!("../.github/workflows/act-validation.yml");

fn path<'a>(value: &'a Value, keys: &[&str]) -> Option<&'a Value> {
    keys.iter().try_fold(value, |parent, key| parent.get(*key))
}

fn string<'a>(value: &'a Value, keys: &[&str]) -> Option<&'a str> {
    path(value, keys).and_then(Value::as_str)
}

fn parse_workflow(source: &str) -> Result<Value, serde_yaml::Error> {
    serde_yaml::from_str::<serde_yaml::Mapping>(source)?;
    serde_yaml::from_str(source)
}

/// Measured coverage needs lld without the development-only linker or frontend.
fn coverage_flags_are_isolated(flags: &str) -> bool {
    flags.contains("-fuse-ld=lld")
        && !flags.contains("-Zthreads=8")
        && !flags.contains("-fuse-ld=mold")
}

fn coverage_step_is_safe(step: &Value) -> bool {
    string(step, &["env", "CARGO_PROFILE_DEV_CODEGEN_BACKEND"]) == Some("llvm")
        && string(step, &["env", "RUSTFLAGS"]).is_some_and(coverage_flags_are_isolated)
}

/// Every job must set up Rust once, preserving Cargo's development defaults.
///
/// Both required profiles are built with Cranelift, so only measured coverage
/// may select another backend, and it does so on its own step.
fn setup_problem(steps: &[Value]) -> Option<&'static str> {
    let setup = steps
        .iter()
        .filter(|step| string(step, &["name"]) == Some("Setup Rust"));
    if setup.count() != 1 {
        return Some("expected one Rust setup step");
    }
    if !steps.iter().any(|step| {
        string(step, &["name"]) == Some("Setup Rust")
            && string(step, &["with", "rustflags"]) == Some("")
    }) {
        return Some("Rust setup must preserve Cargo defaults");
    }
    None
}

/// A coverage step must measure the native-only profile on the LLVM backend.
fn coverage_step_problem(step: &Value) -> Option<&'static str> {
    if !coverage_step_is_safe(step) {
        return Some("coverage must use LLVM and lld without development flags");
    }
    // DL-03/DL-18: the pull-request lane and the `main` baseline must measure
    // the same features or the ratchet compares two different builds.
    if string(step, &["with", "with-default-features"]) != Some("false")
        || string(step, &["with", "features"]) != Some("")
    {
        return Some("coverage must name the native-only profile explicitly");
    }
    None
}

/// A job either measures coverage once or not at all, and ordinary tests keep Cranelift.
fn measured_coverage_problem(steps: &[Value]) -> Option<&'static str> {
    let coverage = steps
        .iter()
        .filter(|step| is_coverage_step(step))
        .collect::<Vec<_>>();
    if coverage.len() > 1 {
        return Some("expected at most one measured coverage step");
    }
    if let Some(problem) = coverage
        .first()
        .and_then(|step| coverage_step_problem(step))
    {
        return Some(problem);
    }
    if steps.iter().any(|step| {
        string(step, &["run"]) == Some("make test")
            && path(step, &["env", "CARGO_PROFILE_DEV_CODEGEN_BACKEND"]).is_some()
    }) {
        return Some("ordinary tests must retain Cranelift");
    }
    None
}

/// Selects the measured coverage action by its shared-actions path.
fn is_coverage_step(step: &Value) -> bool {
    string(step, &["uses"]).is_some_and(|action| action.contains("/generate-coverage@"))
}

/// Explain a hosted job's first missing backend or setup requirement.
fn hosted_job_problem(job: &Value) -> Option<&'static str> {
    let Some(steps) = path(job, &["steps"]).and_then(Value::as_sequence) else {
        return Some("missing hosted job steps");
    };
    setup_problem(steps).or_else(|| measured_coverage_problem(steps))
}

#[test]
fn hosted_coverage_selects_llvm_and_excludes_development_flags() {
    for (file, source) in [("ci.yml", CI), ("coverage-main.yml", MAIN)] {
        let document = parse_workflow(source).expect("parse hosted workflow with unique keys");
        let jobs = path(&document, &["jobs"])
            .and_then(Value::as_mapping)
            .expect("read hosted workflow jobs");
        assert!(
            !jobs.is_empty(),
            "{file} must contain a hosted coverage job"
        );
        let measuring = jobs
            .values()
            .filter(|job| {
                path(job, &["steps"])
                    .and_then(Value::as_sequence)
                    .is_some_and(|steps| steps.iter().any(is_coverage_step))
            })
            .count();
        assert_eq!(
            measuring, 1,
            "{file} must measure coverage in exactly one job; a second measurement would split \
             the ratchet baseline"
        );
        for (name, job) in jobs {
            let problem = hosted_job_problem(job);
            assert!(
                problem.is_none(),
                "{file} job {name:?} backend route failed: {problem:?}"
            );
        }
    }
}

/// One job's step sequence, so an absent job fails rather than passing vacuously.
fn job_steps<'a>(document: &'a Value, job: &str) -> &'a [Value] {
    path(document, &["jobs", job, "steps"])
        .and_then(Value::as_sequence)
        .map_or_else(|| panic!("{job} must declare steps"), Vec::as_slice)
}

/// The Polars jobs must not measure coverage; the native-only job owns it.
#[test]
fn only_the_native_only_job_measures_coverage() {
    let document = parse_workflow(CI).expect("parse the hosted coverage fixture");
    for name in ["polars-lint", "polars-test"] {
        assert!(
            !job_steps(&document, name).iter().any(is_coverage_step),
            "{name} must not publish a second coverage measurement"
        );
        assert_eq!(
            string(&document, &["jobs", name, "env", "GATE_PROFILE"]),
            Some("polars-enabled"),
            "{name} must select the Polars-enabled profile"
        );
    }
    assert_eq!(
        string(&document, &["jobs", "build-test", "env", "GATE_PROFILE"]),
        Some("native-only"),
        "build-test must select the profile its coverage artefact measures"
    );
}

#[test]
fn hosted_coverage_rejects_inherited_dev_flags() {
    let document = parse_workflow(CI).expect("parse the hosted coverage fixture");
    let steps = path(&document, &["jobs", "build-test", "steps"])
        .and_then(Value::as_sequence)
        .expect("read CI's coverage route");
    let coverage = steps
        .iter()
        .find(|step| {
            string(step, &["uses"]).is_some_and(|action| action.contains("/generate-coverage@"))
        })
        .expect("find CI's coverage action");
    for flags in [
        "-D warnings -Zthreads=8 -C link-arg=-fuse-ld=lld",
        "-D warnings -C link-arg=-fuse-ld=mold",
        "-D warnings",
    ] {
        let mut mutated = coverage.clone();
        mutated
            .get_mut("env")
            .and_then(Value::as_mapping_mut)
            .expect("edit a coverage environment")
            .insert(
                Value::String("RUSTFLAGS".to_owned()),
                Value::String(flags.to_owned()),
            );
        assert!(
            !coverage_step_is_safe(&mutated),
            "a mutated hosted coverage flag set must fail isolation: {flags}"
        );
    }
}

#[test]
fn act_setup_preserves_cranelift_defaults() {
    let document = parse_workflow(ACT).expect("parse Act workflow with unique keys");
    let steps = path(&document, &["jobs", "act-validation", "steps"])
        .and_then(Value::as_sequence)
        .expect("read Act job steps");
    let setup = steps
        .iter()
        .find(|step| string(step, &["name"]) == Some("Setup Rust"))
        .expect("find Act's Rust setup");
    assert!(
        string(setup, &["uses"])
            .is_some_and(|action| action.ends_with("@47b337e4f230b591891656534d4ffad868131740")),
        "Act must use the setup action that supports rustflags passthrough"
    );
    assert_eq!(
        string(setup, &["with", "rustflags"]),
        Some(""),
        "Act Rust setup must leave Cargo's defaults active"
    );
}
