//! Scratch facade consumes the same dependency-free kernel body.
#![no_std]
#[cfg(kani)]
mod verification {
    //! A compiler-compatibility observation with a reachable target witness.
    #[kani::proof]
    fn target_facts() {
        let width = probe_kernel::TargetFacts::current().usize_bits();
        assert!(width == usize::BITS, "the kernel must report this target's width");
        kani::cover!(width == 64, "the supported target has a reachable 64-bit width");
    }
}
