//! FACADE-7's local half: the public surface is non-generic and transferable.
//!
//! A downstream program must be able to name every type in a signature, move
//! a value between threads, and store one in a `Box<dyn Error>`. A generic
//! parameter or a non-`Send` interior would pass every behavioural test on one
//! thread and break that program. The end-to-end fixture proves the rest of
//! FACADE-7 from outside the workspace.

use combobulate::{AExpr, Array, ExpressionError, Failure, NativeExecutor, PreparedPlan, add};

use super::{engine, expr};

/// Asserts that a type is `Send` and `Sync`.
fn assert_send_sync<T: Send + Sync>() {}

#[test]
fn every_public_type_is_send_and_sync() {
    assert_send_sync::<AExpr>();
    assert_send_sync::<Array>();
    assert_send_sync::<PreparedPlan>();
    assert_send_sync::<ExpressionError>();
    assert_send_sync::<NativeExecutor>();
    assert_send_sync::<Failure>();
    assert_send_sync::<combobulate::OperationId>();
    assert_send_sync::<combobulate::Dtype>();
    assert_send_sync::<combobulate::Stage>();
    assert_send_sync::<combobulate::Unary>();
    assert_send_sync::<combobulate::Binary>();
}

#[test]
fn every_public_type_has_a_non_generic_name() {
    let names = [
        core::any::type_name::<AExpr>(),
        core::any::type_name::<Array>(),
        core::any::type_name::<PreparedPlan>(),
        core::any::type_name::<ExpressionError>(),
        core::any::type_name::<NativeExecutor>(),
        core::any::type_name::<Failure>(),
        core::any::type_name::<combobulate::OperationId>(),
        core::any::type_name::<combobulate::Dtype>(),
        core::any::type_name::<combobulate::Stage>(),
        core::any::type_name::<combobulate::Unary>(),
        core::any::type_name::<combobulate::Binary>(),
    ];
    for name in names {
        assert!(
            !name.contains('<'),
            "every public type must be non-generic, but {name} has a parameter"
        );
    }
}

#[test]
fn an_expression_moves_between_threads() {
    let expression = add().apply(&expr(&[1, 2]), &expr(&[10, 20]));
    let worker = std::thread::spawn(move || {
        expression
            .collect()
            .expect("threads must be able to run the ordinary path")
            .as_i64_slice()
            .map(<[i64]>::to_vec)
    });
    assert_eq!(
        worker.join().expect("the worker must finish"),
        Some(vec![11, 22]),
        "a moved expression must evaluate where it lands"
    );
}

#[test]
fn a_plan_moves_between_threads() {
    let plan = expr(&[1, 2])
        .prepare(&engine())
        .expect("an input has no shape to disagree about");
    let worker = std::thread::spawn(move || {
        plan.execute()
            .expect("an input cannot overflow")
            .as_i64_slice()
            .map(<[i64]>::to_vec)
    });
    assert_eq!(
        worker.join().expect("the worker must finish"),
        Some(vec![1, 2]),
        "a plan must execute on whatever thread holds it"
    );
}

#[test]
fn an_error_can_be_stored_as_a_boxed_std_error() {
    let error: Box<dyn core::error::Error + Send + Sync> = Box::new(
        add()
            .apply(&expr(&[1, 2, 3]), &expr(&[1, 2]))
            .prepare(&engine())
            .expect_err("unequal lengths cannot be prepared"),
    );
    assert!(
        error.to_string().contains("preparation"),
        "the boxed error must still say which stage failed"
    );
}

#[test]
fn the_engine_is_constructible_only_through_its_constructor() {
    let built = NativeExecutor::sequential();
    let defaulted = NativeExecutor::default();
    assert_eq!(
        built, defaulted,
        "the sequential engine must be the default one"
    );
}
