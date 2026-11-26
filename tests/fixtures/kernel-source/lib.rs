//! A clean kernel-shaped crate root for the VO-6 non-vacuity seed.
//!
//! The root is deliberately faultless, so the only violations the widened scan
//! can report are the ones seeded in this tree's operation module. A root-only
//! scan passes this file, which is exactly why a fixture like it proves the
//! submodule walk rather than merely illustrating it. Nothing compiles the
//! file: it is read as text by `tests/workspace_kernel_boundary.rs`.
#![no_std]
#![deny(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]

pub mod elementwise_add;
