//! An ordinary downstream program that uses the facade's expression path.
//!
//! `tests/native_consumer_e2e.rs` builds and runs this binary beside the
//! profile binary, so FACADE-7 is proved by a real consumer rather than by a
//! test inside the workspace: it names every public type in a signature, runs
//! the three phases a caller uses, and never mentions the kernel crate.
//!
//! Only the public API appears here. A type that grew a type parameter, a
//! method that needed a trait import, or an error that could not be formatted
//! would fail to compile in this crate, which is outside the workspace and
//! takes the facade with default features off.

use combobulate::{Array, NativeExecutor, add, identity};

/// Runs the program's three phases and prints one line each.
fn main() {
    let values = vec![1_i64, 2, 3];
    let input = Array::from_i64(values);
    let shared = input.expr().then(&identity());
    let identity_keeps_the_buffer = shared
        .collect()
        .is_ok_and(|array| array.as_i64_slice().map(<[i64]>::as_ptr) == buffer_of(&input));
    println!(
        "identity: {:?} (shared buffer: {identity_keeps_the_buffer})",
        shared
            .collect()
            .ok()
            .and_then(|array| array.as_i64_slice().map(<[i64]>::to_vec))
            .unwrap_or_default()
    );

    let right = Array::from_i64(vec![10, 20, 30]);
    let sum = add().apply(&input.expr(), &right.expr());
    println!(
        "add: {:?}",
        sum.collect()
            .ok()
            .and_then(|array| array.as_i64_slice().map(<[i64]>::to_vec))
            .unwrap_or_default()
    );

    let prepared = sum.prepare(&NativeExecutor::sequential());
    let collected = prepared.and_then(|plan| plan.execute());
    println!(
        "collect: {:?}",
        collected
            .ok()
            .and_then(|array| array.as_i64_slice().map(<[i64]>::to_vec))
            .unwrap_or_default()
    );
}

/// The buffer of an array, or `None` when it has no elements.
fn buffer_of(array: &Array) -> Option<*const i64> { array.as_i64_slice().map(<[i64]>::as_ptr) }
