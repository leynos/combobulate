"""Guard the verifier-free image recipe against a missing `mold` runtime library."""

import unittest

from verifier_probe_loader import load_verifier_probes


class VerifierFreeContainerTests(unittest.TestCase):
    """Check the container recipe can run the pinned `mold` linker."""

    def test_containerfile_installs_the_pinned_mold_runtime_library(self) -> None:
        """Clang pulls in no libatomic, so the recipe must name it explicitly."""
        recipe = load_verifier_probes().verifier_free_containerfile()

        self.assertTrue(recipe.startswith('FROM quay.io/rockylinux/'), 'the recipe must start from the pinned base image')
        self.assertIn('clang gcc-c++ make libatomic', recipe, 'the recipe must install `mold`\'s runtime library')