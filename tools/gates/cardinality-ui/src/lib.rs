//! Library target required by `trybuild`'s generated crate.
//!
//! `trybuild` adds the package under test to the generated manifest by path, so
//! the package needs a library target even though the gate's content is all in
//! its `tests` directory.
