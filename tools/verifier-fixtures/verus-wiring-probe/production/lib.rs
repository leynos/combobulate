//! Ordinary dependency-free crate containing the shared executable module.
#![no_std]
#[path = "../production.rs"]
mod implementation;
pub use implementation::increment;
