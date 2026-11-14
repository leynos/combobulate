//! FACADE-1: execution refines the abstract model on generated graphs.
//!
//! A finite table cannot cover the shapes an expression can take, so the
//! refinement claim is checked against a generator. Each generated graph is
//! rebuilt into an independent oracle — a memoizing evaluator written against
//! the model, sharing no code with the crate and never calling the kernel — and
//! the two are compared.
//!
//! The oracle states the whole lifecycle contract, not just the denotation:
//! `collect` is `prepare` followed by `execute`, so a graph with a static
//! disagreement must report that disagreement rather than the value error its
//! operands would have produced. Comparing `collect` against the bare
//! denotation instead would flag that intended precedence as a defect.
//!
//! A generator that silently stopped producing interesting cases would pass
//! every comparison, so a companion test counts what the strategy draws and
//! requires a minimum of each outcome the plan names.
//!
//! Generated graphs are bounded in size. The bound keeps the cases readable: an
//! unbounded chain fails first at the heap, not at the model, and the deep-chain
//! requirement is FACADE-5's job.
//!
//! The case is split by responsibility so each part reads on its own:
//!
//! - `generator` draws graphs and builds the crate's expression for one;
//! - `model` states the specification's lengths and denotations;
//! - `verdict` turns a run, and a graph, into the model's own vocabulary;
//! - `checks` compares the two and counts what the generator draws.

mod checks;
mod generator;
mod model;
mod verdict;
