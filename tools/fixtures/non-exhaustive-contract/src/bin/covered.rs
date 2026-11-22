//! The compile-**pass** half of the facade's `#[non_exhaustive]` contract.
//!
//! `tests/non_exhaustive_contract.rs` builds this binary and requires it to
//! succeed. It is the evidence that a downstream caller can still use every
//! non-exhaustive type the way the documentation says: match with a wildcard or
//! `..`, read what a real run reported, and build the engine through its
//! constructor. A contract that had hardened into "unusable outside the crate"
//! would fail this file's own compilation.
//!
//! Its sibling `exhaustive.rs` states the other direction and is expected never
//! to build.

use combobulate::{Array, Dtype, Failure, NativeExecutor, Stage, add};

/// Names the [`Dtype`] a value holds, allowing for a variant added later.
fn describe_dtype(dtype: Dtype) -> &'static str {
    match dtype {
        Dtype::I64 => "i64",
        // The wildcard is what `#[non_exhaustive]` requires of a caller, and
        // writing it here is the behaviour the attribute exists to force.
        _ => "another dtype",
    }
}

/// Names the [`Stage`] a failure came from.
fn describe_stage(stage: Stage) -> &'static str {
    match stage {
        Stage::Preparation => "preparation",
        Stage::Execution => "execution",
        _ => "another stage",
    }
}

/// Reads a [`Failure`]'s code and its fields through the `..` pattern.
///
/// A struct-variant pattern is how a caller destructures a non-exhaustive
/// variant: naming every field would break when a later release adds one, so
/// `..` is the form that keeps compiling.
fn describe_failure(failure: Failure) -> String {
    match failure {
        Failure::ShapeAgreement { lhs_len, rhs_len, .. } => {
            format!("ShapeAgreement({lhs_len}, {rhs_len})")
        }
        Failure::IntegerOverflow { position, .. } => format!("IntegerOverflow({position})"),
        _ => "another failure".to_owned(),
    }
}

/// Builds the engine the only two ways a caller may.
fn engines() -> (NativeExecutor, NativeExecutor) {
    (NativeExecutor::sequential(), NativeExecutor::default())
}

fn main() {
    let engine = engines().0;
    let values = Array::from_i64(vec![1, 2, 3]);
    println!("dtype: {}", describe_dtype(values.dtype()));

    let error = add()
        .apply(&values.expr(), &Array::from_i64(vec![1, 2]).expr())
        .prepare(&engine)
        .expect_err("operands of different lengths cannot be prepared");
    let failures = error.failures().to_vec();
    println!(
        "stage: {}; failures: {}",
        describe_stage(error.stage()),
        failures.into_iter().map(describe_failure).collect::<Vec<String>>().join(", ")
    );
}
