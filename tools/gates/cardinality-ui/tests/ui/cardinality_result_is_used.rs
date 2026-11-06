//! Accept code that binds the overflow-sensitive cardinality result.
#![deny(unused_must_use)]

use cardinality_probe::checked_cardinality;

fn main() {
    let _ = checked_cardinality(&[usize::MAX, 2]);
}
