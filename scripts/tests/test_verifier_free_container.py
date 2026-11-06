"""Guard the verifier-free image recipe and its container invocation."""

import unittest
from pathlib import Path

from verifier_probe_loader import load_verifier_free_probe, load_verifier_probes


class VerifierFreeContainerTests(unittest.TestCase):
    """Check the container recipe can run the pinned `mold` linker."""

    def test_containerfile_installs_the_pinned_mold_runtime_library(self) -> None:
        """Clang pulls in no libatomic, so the recipe must name it explicitly."""
        recipe = load_verifier_probes()._verifier_free_containerfile()

        self.assertTrue(recipe.startswith('FROM quay.io/rockylinux/'), 'the recipe must start from the pinned base image')
        self.assertIn('clang gcc-c++ make libatomic', recipe, 'the recipe must install `mold`\'s runtime library')


class VerifierFreeCommandTests(unittest.TestCase):
    """Keep the container invocation isolated and its mounts unchanged."""

    def test_command_keeps_isolation_mounts_and_build_script(self) -> None:
        """The refactor must preserve every isolation and mount argument."""
        module = load_verifier_free_probe()
        workspace = Path('/tmp/epm1-verifier-free-workspace')
        home = Path('/home/probe')

        command = module.container_run_command(workspace, 'probe:tag', home, 'nightly-2026-08-27')

        self.assertEqual(command[:2], ['podman', 'run'], 'the probe must run through podman')
        for flag in ('--network=none', '--userns=keep-id', '--security-opt=label=disable'):
            self.assertIn(flag, command, f'{flag} keeps the build isolated')
        self.assertIn(f'{workspace}:{workspace}', command, 'the staged workspace must be writable for the build')
        self.assertIn(f'{home}/.cargo:{home}/.cargo', command, 'the Cargo cache must be writable for the build')
        self.assertIn(f'{home}/.local/bin/mold:{home}/.local/bin/mold:ro', command, 'pinned tools must stay read-only')
        self.assertEqual(command[-3:-1], ['bash', '-c'], 'the build script must be the container command')
        self.assertIn('test ! -e "$HOME/.kani"', command[-1], 'the script must prove no verifier is installed')

    def test_verifier_absence_checks_abort_under_errexit(self) -> None:
        """A negated `command -v` cannot fail under `set -e`, so use a branch."""
        script = load_verifier_free_probe().BUILD_SCRIPT

        self.assertNotIn('! command -v', script, 'a negated command cannot abort under `set -e`')
        for verifier in ('verus', 'cargo-kani'):
            guard = f'if command -v {verifier} >/dev/null 2>&1; then'
            self.assertIn(guard, script, f'the {verifier} check must be an explicit branch')
            failure = script.split(guard, 1)[1].split('fi;', 1)[0]
            self.assertIn('exit 1', failure, f'the {verifier} branch must fail the build')