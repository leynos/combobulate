//! The ordinary application path, exercised through the public API only.
//!
//! Each submodule owns one facade obligation (FACADE-1 to FACADE-8). They are
//! separate files so one obligation's evidence can be read without the others'
//! setup, and they are `#[path]` submodules of this one binary so the shared
//! helpers below are one copy, compiled once, rather than a support crate
//! every test binary would rebuild.

#[path = "ordinary_application/copies.rs"]
mod copies;
#[path = "ordinary_application/deep_chain.rs"]
mod deep_chain;
#[path = "ordinary_application/diagnostics.rs"]
mod diagnostics;
#[path = "ordinary_application/failures.rs"]
mod failures;
#[path = "ordinary_application/refinement/mod.rs"]
mod refinement;
#[path = "ordinary_application/sharing.rs"]
mod sharing;
#[path = "ordinary_application/staging.rs"]
mod staging;
#[path = "ordinary_application/surface.rs"]
mod surface;

use combobulate::{AExpr, Array, ExpressionError, Failure, NativeExecutor};

/// The engine every case uses unless it is testing another one.
fn engine() -> NativeExecutor { NativeExecutor::sequential() }

/// A materialized array of the given values.
fn array(values: &[i64]) -> Array { Array::from_i64(values.to_vec()) }

/// A deferred expression over the given values.
fn expr(values: &[i64]) -> AExpr { array(values).expr() }

/// The one failure `error` reports.
///
/// Every execution error in this release holds exactly one failure, and the
/// cases that read it are asserting on that failure rather than on a list. A
/// report of another size is a defect in the case's premise, so the panic says
/// how many were reported.
fn single_failure(error: &ExpressionError) -> &Failure {
    let failures = error.failures();
    let [failure] = failures else {
        panic!(
            "the case expects one failure, the report holds {}: {failures:?}",
            failures.len()
        );
    };
    failure
}

/// The pointer of an array's buffer, or `None` when it has no elements.
///
/// An empty `Vec` may have any pointer, including one another empty buffer
/// shares, so comparing pointers of empty buffers would compare nothing.
fn buffer_ptr(array: &Array) -> Option<*const i64> { array.as_i64_slice().map(<[i64]>::as_ptr) }
