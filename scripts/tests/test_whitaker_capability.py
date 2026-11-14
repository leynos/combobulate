"""Mutation regressions for source-derived Whitaker capability observations."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from whitaker_capability import Scenario, fragments, probe_manifest, run_scenario

FIXTURES = Path(__file__).parent / 'fixtures' / 'whitaker'
MANIFEST = yaml.safe_load((FIXTURES / 'current.yml').read_text())


def fragment(manifest: dict, name: str) -> dict:
    """Find one fixture boundary; mutation assertions prove the selected source changes."""
    return next(step for step in manifest['runs']['steps'] if step['name'] == name)


def legacy_with_declared_cranelift_input() -> dict:
    """Declare the missing input so the probe's behavioural boundaries can run.

    The declaration is the only change: it neither adds Cranelift support nor
    touches either shell fragment, so the result still exposes what the legacy
    installer does rather than what the fixture claims about itself.
    """
    legacy = yaml.safe_load((FIXTURES / 'legacy.yml').read_text())
    adapted = copy.deepcopy(legacy)
    adapted['inputs']['cranelift'] = {
        'description': 'Declared only so the probe reaches the shell boundaries.',
        'required': False,
        'default': 'false',
    }
    return adapted


class CapabilityMutationTests(unittest.TestCase):
    """Each negative fixture removes one protection from capable upstream fragments."""

    def changed_run(self, before: str, after: str) -> dict:
        """Replace actual executable text, not comments naming a capability."""
        changed = copy.deepcopy(MANIFEST)
        step = fragment(changed, 'Run Whitaker installer')
        self.assertIn(before, step['run'])
        step['run'] = step['run'].replace(before, after)
        self.assertNotEqual(changed, MANIFEST)
        return changed

    def test_missing_binary_only_flag_rejects_cold_source_fallback(self):
        """Dropping the flag fails even when the ordinary stub would return success."""
        changed = self.changed_run('set -- --no-source-fallback', 'set --')
        with self.assertRaisesRegex(ValueError, 'arguments'):
            probe_manifest(changed)

    def test_each_flag_arm_is_required_independently(self):
        """Changing just Cranelift or just the ordinary arm cannot pass the probe."""
        # The ordinary-arm mutation keeps the flag when Cranelift is requested, so it
        # cannot be detected through the Cranelift scenario and the ordinary scenario
        # alone has to catch it.
        ordinary_only = ('if [[ "$WHITAKER_CRANELIFT" == "true" ]]; then '
                         'set -- --no-source-fallback; else set --; fi')
        for original, replacement in (('set -- "$@" --cranelift', ':'),
                                      ('set -- --no-source-fallback', ordinary_only)):
            with self.subTest(arm=original):
                changed = self.changed_run(original, replacement)
                with self.assertRaisesRegex(ValueError, 'arguments'):
                    probe_manifest(changed)

    def test_a_bundle_path_is_handed_to_the_installer(self):
        """A non-empty snapshot bundle reaches the installer as its own flag and argument."""
        with self.assertRaisesRegex(ValueError, 'arguments'):
            probe_manifest(self.changed_run('--clippy-snapshot-bundle "$WHITAKER_SNAPSHOT_BUNDLE"',
                                            '--clippy-snapshot-bundle ""'))

    def test_upstream_legacy_fragments_fail_capability_directly(self):
        """Pre-#522 source is unsuitable without any content-approval guard.

        The fixture never declares the Cranelift input, so the probe stops at
        that prerequisite before any shell fragment runs. This is the boundary
        that rejects the legacy manifest once the content-hash gate is gone.
        """
        source = (FIXTURES / 'legacy.yml').read_text()
        with patch('whitaker_capability.run_scenario') as runner:
            with self.assertRaisesRegex(ValueError, 'the action must support the Cranelift input'):
                probe_manifest(yaml.safe_load(source))
            runner.assert_not_called()

    def test_legacy_binary_only_and_missing_asset_boundaries_fail_behaviourally(self):
        """Legacy source fails on what it does, not on a stale content digest.

        Declaring the Cranelift input lets the probe reach the shell
        boundaries. The first scenario then observes that the legacy installer
        receives no binary-only arguments, and a direct missing-asset run
        observes that it builds from source instead of failing. Both results
        are simulated markers from the probe's fake installer, not a real
        build.
        """
        adapted = legacy_with_declared_cranelift_input()
        with self.assertRaisesRegex(ValueError, 'installer arguments violate binary-only policy'):
            probe_manifest(adapted)
        with self.assertRaisesRegex(ValueError, 'missing assets permitted a source build'):
            run_scenario(fragments(adapted), Scenario(missing_asset=True), 'cold-missing-artifact')

    def test_ignored_installer_failure_is_rejected(self):
        """A command failure must survive the tee pipeline and action backstop."""
        changed = self.changed_run('if (( installer_status != 0 )); then', 'if false; then')
        with self.assertRaisesRegex(ValueError, 'installer-failure'):
            probe_manifest(changed)

    def test_missing_both_stream_backstop_is_rejected(self):
        """Source-fallback output can never count as a successful prebuilt install."""
        changed = self.changed_run('if [[ "$suite_source" == "source" ]]; then', 'if false; then')
        with self.assertRaisesRegex(ValueError, 'source-stdout'):
            probe_manifest(changed)

    def test_stdout_only_backstop_is_rejected(self):
        """A Dylint fallback on stderr exposes the original pre-#522 blind spot."""
        changed = self.changed_run('"$installer_log" "$installer_err"; then', '"$installer_log"; then')
        with self.assertRaisesRegex(ValueError, 'source-stderr'):
            probe_manifest(changed)

    def test_conditional_ci_mode_fallback_is_rejected(self):
        """Disabling the published-asset precheck cannot permit source builds."""
        changed = self.changed_run('if [[ "$suite_source" == "source" ]]; then',
                                   'if [[ "$suite_source" == "source" && "${WHITAKER_CI_MODE:-true}" == true ]]; then')
        fragment(changed, 'Run Whitaker installer')['env']['WHITAKER_CI_MODE'] = '${{ inputs.ci-mode }}'
        with self.assertRaisesRegex(ValueError, 'source-stderr'):
            probe_manifest(changed)

    def test_suite_pin_refusal_is_observed_before_installation(self):
        """Removing validation's explicit suite-pin refusal cannot pass the probe."""
        changed = copy.deepcopy(MANIFEST)
        step = fragment(changed, 'Validate Whitaker inputs')
        anchor = 'if [[ -n "$SUITE_VERSION_INPUT" ]]; then'
        self.assertIn(anchor, step['run'])
        step['run'] = step['run'].replace(anchor, 'if false; then')
        with self.assertRaisesRegex(ValueError, 'prohibited'):
            probe_manifest(changed)

    def test_removed_version_floor_is_rejected(self):
        """An action that accepts installer 0.2.8 cannot carry the required flag contract."""
        changed = copy.deepcopy(MANIFEST)
        step = fragment(changed, 'Validate Whitaker inputs')
        anchor = 'if (( version_major == 0 && (version_minor < 2 || (version_minor == 2 && version_patch < 9)) )); then'
        self.assertIn(anchor, step['run'])
        step['run'] = step['run'].replace(anchor, 'if false; then')
        with self.assertRaisesRegex(ValueError, 'prohibited'):
            probe_manifest(changed)

    def test_guarded_run_boundary_is_rejected(self):
        """A feature probe must not silently ignore a real conditional bypass."""
        changed = copy.deepcopy(MANIFEST)
        fragment(changed, 'Run Whitaker installer')['if'] = False
        with self.assertRaisesRegex(ValueError, 'skipped'):
            probe_manifest(changed)

    def test_substituted_validation_output_is_rejected(self):
        """The run fixture cannot mask a changed path produced by validation itself."""
        changed = copy.deepcopy(MANIFEST)
        step = fragment(changed, 'Validate Whitaker inputs')
        anchor = '"${cargo_home}/bin/whitaker-installer${installer_suffix}"'
        self.assertIn(anchor, step['run'])
        step['run'] = step['run'].replace(anchor, '"/unrelated/installer"')
        with self.assertRaisesRegex(ValueError, 'private installer path'):
            probe_manifest(changed)

    def test_unexpected_download_executor_is_refused(self):
        """Behavioural fragments use denied offline executors for network/build commands."""
        changed = copy.deepcopy(MANIFEST)
        step = fragment(changed, 'Run Whitaker installer')
        step['run'] += '\ncurl https://fixture.invalid\n'
        with self.assertRaisesRegex(ValueError, 'network/build'):
            probe_manifest(changed)
