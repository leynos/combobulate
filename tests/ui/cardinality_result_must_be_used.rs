//! Reject code that discards the overflow-sensitive cardinality result.
#![deny(unused_must_use)]

use cardinality_probe::checked_cardinality;

fn main() {
    checked_cardinality(&[usize::MAX, 2]);
}
