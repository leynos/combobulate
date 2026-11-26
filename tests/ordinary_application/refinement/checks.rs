//! The checks: the model comparisons, and the count that keeps them honest.
//!
//! Both comparisons run under one configuration. Persistence is off: a shrunk
//! counterexample becomes a named case, and a test binary's module tree gives
//! `proptest` no single source file to write beside.
//!
//! The count is what stops a generator quietly drawing only easy shapes. It
//! runs the same strategy through a fixed-seed runner and requires a minimum of
//! each outcome the plan names. Minimums rather than exact counts, because the
//! random stream may change on a `proptest` upgrade.

use std::cell::RefCell;

use combobulate::{AExpr, Stage, add, identity};
use proptest::{
    prelude::*,
    test_runner::{Config, TestRng, TestRunner},
};

use super::{
    generator::{Graph, NodeSpec, graph, shares},
    model::{self, Outcome},
    verdict::{Verdict, expectation, observed, observed_preparation, stage_word},
};

/// How many draws the companion count makes.
const DRAWS: u32 = 512;

/// The configuration every model check runs under.
fn model_config() -> Config {
    Config {
        cases: DRAWS,
        failure_persistence: None,
        ..Config::default()
    }
}

/// Builds the crate's expression for `graph`.
fn build(graph: &Graph) -> AExpr {
    let mut nodes: Vec<AExpr> = graph
        .inputs
        .iter()
        .map(|values| super::super::expr(values))
        .collect();
    for spec in &graph.nodes {
        nodes.push(apply(&nodes, spec));
    }
    nodes
        .pop()
        .expect("a graph always holds at least one input")
}

/// Applies one drawn operation to the nodes before it.
fn apply(nodes: &[AExpr], spec: &NodeSpec) -> AExpr {
    match spec {
        NodeSpec::Identity { of } => at(nodes, *of).then(&identity()),
        NodeSpec::Add { lhs, rhs } => add().apply(&at(nodes, *lhs), &at(nodes, *rhs)),
    }
}

/// The expression already built for node `index`.
fn at(nodes: &[AExpr], index: usize) -> AExpr {
    nodes
        .get(index)
        .expect("every generated node names an earlier one")
        .clone()
}

proptest! {
    #![proptest_config(model_config())]

    /// `collect` is `prepare` followed by `execute`, on generated graphs.
    #[test]
    fn collect_matches_the_lifecycle_contract(graph in graph()) {
        let expression = build(&graph);
        prop_assert_eq!(
            observed(&expression),
            expectation(&graph),
            "collect must prepare, then execute"
        );
    }

    /// Preparation reports exactly the model's root-cause disagreements.
    #[test]
    fn preparation_reports_the_models_static_failures(graph in graph()) {
        let expression = build(&graph);
        let expected: Vec<Option<Outcome>> = model::static_failures(&graph)
            .into_iter()
            .map(Some)
            .collect();
        prop_assert_eq!(
            observed_preparation(&expression),
            expected,
            "preparation must report the model's failures in its order"
        );
    }
}

#[test]
fn the_generator_draws_every_outcome_it_must() {
    let config = model_config();
    let algorithm = config.rng_algorithm;
    let mut runner = TestRunner::new_with_rng(config, TestRng::deterministic_rng(algorithm));
    let drawn = RefCell::new(Counts::default());
    runner
        .run(&graph(), |graph| {
            drawn.borrow_mut().observe(&graph);
            Ok(())
        })
        .expect("the generator must not fail its own run");
    let counts = drawn.into_inner();
    assert!(
        counts.ok_wide >= 8,
        "the generator must draw sums of two or more values, got {counts:?}"
    );
    assert!(
        counts.overflow_late >= 4,
        "the generator must draw an overflow above position zero, got {counts:?}"
    );
    assert!(
        counts.shape_pair >= 2,
        "the generator must draw two independent disagreements, got {counts:?}"
    );
    assert!(
        counts.shared_ok >= 4,
        "the generator must draw a successful run through a shared subterm, got {counts:?}"
    );
}

/// How many of each outcome the companion count observed.
#[derive(Debug, Default)]
struct Counts {
    /// Successful runs with two or more values.
    ok_wide: usize,
    /// Successful runs with fewer than two values.
    ok_narrow: usize,
    /// Runs that failed at execution with an overflow above position zero.
    overflow_late: usize,
    /// Runs that failed at execution with an overflow at position zero.
    overflow_first: usize,
    /// Runs that failed at preparation.
    shape: usize,
    /// Preparation runs that reported two or more failures.
    shape_pair: usize,
    /// Successful runs whose graph shares a node between consumers.
    shared_ok: usize,
}

impl Counts {
    /// Records what one generated graph produced.
    fn observe(&mut self, graph: &Graph) {
        match expectation(graph) {
            Verdict::Values(values) if values.len() >= 2 => {
                self.ok_wide += 1;
                if shares(graph) {
                    self.shared_ok += 1;
                }
            }
            Verdict::Values(_) => self.ok_narrow += 1,
            Verdict::Failed { stage, failures } => self.observe_failure(stage, &failures),
        }
    }

    /// Records one failing run.
    fn observe_failure(&mut self, stage: &'static str, failures: &[Option<Outcome>]) {
        if stage == stage_word(Stage::Execution) {
            match failures.first() {
                Some(Some(Outcome::Overflow { position })) if *position > 0 => {
                    self.overflow_late += 1;
                }
                _ => self.overflow_first += 1,
            }
        } else {
            self.shape += 1;
            if failures.len() >= 2 {
                self.shape_pair += 1;
            }
        }
    }
}
