"""Hermetic manifest acquisition and caller-binding regressions for Whitaker CI."""
from __future__ import annotations

import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from whitaker_probe import NoRedirects, document, fetch_manifest, fetch_source, main, verify_workflow
from test_whitaker_capability import legacy_with_declared_cranelift_input

FIXTURES = Path(__file__).parent / 'fixtures' / 'whitaker'
CAPABLE = (FIXTURES / 'current.yml').read_text()
LEGACY = (FIXTURES / 'legacy.yml').read_text()
ACTION = 'leynos/shared-actions/.github/actions/install-whitaker'


def caller(reference: str) -> str:
    """Build a workflow whose actual candidate ref is independent of fixture source."""
    return f'jobs:\n  build-test:\n    steps:\n      - uses: {ACTION}@{reference}\n'


def multi_job_caller(references: dict[str, str]) -> str:
    """Build one required job per reference; e.g. two jobs pinning two commits."""
    jobs = ''.join(
        f'  {name}:\n    steps:\n      - uses: {ACTION}@{reference}\n'
        for name, reference in references.items()
    )
    return f'jobs:\n{jobs}'


class SourceBindingTests(unittest.TestCase):
    """A shape-valid SHA is accepted only after its own resolved manifest passes probes."""

    def test_same_behaviour_at_multiple_resolved_refs_passes(self):
        """A pin-only Dependabot bump passes even when harmless content changes."""
        changed = CAPABLE + '\n# harmless trailing comment\n'
        candidates = [('a' * 40, CAPABLE), ('b' * 40, changed)]
        seen = []
        for reference, manifest in candidates:
            def acquire(current, path, manifest=manifest):
                """Serve the candidate manifest for the one supported path."""
                seen.append((current, path))
                return manifest
            evidence = verify_workflow(caller(reference), acquire)
            self.assertEqual(evidence['reference'], reference)
            self.assertEqual(evidence['manifest_sha256'], hashlib.sha256(manifest.encode()).hexdigest())
            self.assertEqual(evidence['scenarios'], 14)
        self.assertEqual(seen, [(reference, 'action.yml') for reference, _ in candidates],
                         'each ref must fetch exactly the manifest')
        self.assertNotEqual(
            hashlib.sha256(CAPABLE.encode()).hexdigest(),
            hashlib.sha256(changed.encode()).hexdigest(),
            'the harmless change must still alter the provenance digest')

    def test_every_calling_job_must_pin_the_same_reviewed_source(self):
        """A second job cannot install a different Whitaker build.

        DL-03 puts the installer in more than one required job, so the caller
        reference is resolved per job. One shared reference has one manifest to
        probe; two different references bind no single source and fail.
        """
        seen = []

        def acquire(current, path):
            """Record the single manifest fetch made for every requesting job."""
            seen.append((current, path))
            return CAPABLE

        evidence = verify_workflow(
            multi_job_caller({'build-test': 'a' * 40, 'polars-lint': 'a' * 40}), acquire)
        self.assertEqual(evidence['reference'], 'a' * 40)
        self.assertEqual(seen, [('a' * 40, 'action.yml')],
                         'the manifest must be fetched exactly once at the shared ref')
        with self.assertRaisesRegex(ValueError, 'same Whitaker reference'):
            verify_workflow(
                multi_job_caller({'build-test': 'a' * 40, 'polars-lint': 'b' * 40}),
                lambda *_: self.fail('a split reference must not be fetched'))

    def test_repeated_installer_in_one_job_is_rejected(self):
        """One job installing Whitaker twice would run two builds behind one gate."""
        source = ('jobs:\n  build-test:\n    steps:\n'
                  f'      - uses: {ACTION}@{"a" * 40}\n'
                  f'      - uses: {ACTION}@{"a" * 40}\n')
        with self.assertRaisesRegex(ValueError, 'exactly one Whitaker installer'):
            verify_workflow(source, lambda *_: self.fail('a repeated installer must not be fetched'))

    def test_old_capability_is_rejected_despite_valid_sha_shape(self):
        """The pre-#522 manifest fails behaviourally, not on a content digest.

        The adapted copy declares only the Cranelift input so the probe can
        reach the shell boundary; it neither adds Cranelift support nor changes
        an installer fragment, and the binary-only argument policy rejects it.
        """
        adapted = yaml.safe_dump(legacy_with_declared_cranelift_input(), sort_keys=False)
        with self.assertRaisesRegex(ValueError, 'binary-only policy'):
            verify_workflow(caller('c' * 40), lambda *_: adapted)

    def test_unmodified_legacy_manifest_fails_the_cranelift_prerequisite(self):
        """The real legacy manifest stops at the first capability boundary."""
        with self.assertRaisesRegex(ValueError, 'the action must support the Cranelift input'):
            verify_workflow(caller('c' * 40), lambda *_: LEGACY)

    def test_unknown_reference_cannot_borrow_a_capable_fixture(self):
        """Nonexistent refs fail acquisition; an unrelated good manifest proves nothing."""
        available = {'a' * 40: CAPABLE}
        with self.assertRaises(KeyError):
            verify_workflow(caller('0' * 40), lambda ref, _: available[ref])

    def test_invalid_reference_is_rejected_before_acquisition(self):
        """Floating, short, nonhex and uppercase refs never reach the source fetcher."""
        for reference in ('main', 'a' * 39, 'G' * 40, 'A' * 40):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                verify_workflow(caller(reference), lambda *_: self.fail('must not fetch'))

    def test_safe_yaml_rejects_duplicates_and_python_objects(self):
        """Both unsafe constructors and ambiguous mapping replacement fail closed."""
        for source in ('name: first\nname: second', '!!python/object/apply:os.system [echo bad]'):
            with self.subTest(source=source), self.assertRaises((ValueError, yaml.YAMLError)):
                document(source)

    def test_manifest_size_limit_applies_to_injected_fetchers(self):
        """Offline acquisition cannot bypass the same source size bound as HTTPS."""
        with patch('whitaker_probe.probe_manifest') as probe:
            with self.assertRaisesRegex(ValueError, 'size limit'):
                verify_workflow(caller('a' * 40), lambda *_: 'x' * (128 * 1024 + 1))
            probe.assert_not_called()

    def test_fetch_uses_exact_pinned_url_and_timeout(self):
        """A fake response tests acquisition arguments without performing a request."""
        class Response:
            """Return one fixture payload through the response context-manager interface."""

            def __enter__(self):
                """Return the fixture response itself for a with statement."""
                return self

            def __exit__(self, *_):
                """Leave response exceptions visible to the caller."""
                return False
            def read(self, _):
                """Yield the configured fixture bytes once, then return EOF."""
                value = getattr(self, 'source', CAPABLE.encode())
                self.source = b''
                return value
        with patch('whitaker_probe.urllib.request.build_opener') as factory:
            factory.return_value.open.return_value = Response()
            self.assertEqual(fetch_manifest('a' * 40), CAPABLE)
            factory.return_value.open.assert_called_once_with(
                'https://raw.githubusercontent.com/leynos/shared-actions/' + 'a' * 40 +
                '/.github/actions/install-whitaker/action.yml', timeout=10)

    def test_http_acquisition_failure_is_not_capability_success(self):
        """A resolver failure cannot cause the CLI pipeline to fall back to a snapshot."""
        with patch('whitaker_probe.urllib.request.build_opener') as factory:
            factory.return_value.open.side_effect = OSError('source unavailable')
            with self.assertRaisesRegex(OSError, 'source unavailable'):
                verify_workflow(caller('a' * 40))

    def test_transport_refuses_redirects_and_unreviewed_paths(self):
        """Neither a new host nor any path but the manifest can enter acquisition."""
        with self.assertRaisesRegex(ValueError, 'redirected'):
            NoRedirects().redirect_request(None, None, 302, '', {}, 'https://fixture.invalid')
        with patch('whitaker_probe.urllib.request.build_opener') as factory:
            for path in ('../other-action/run.sh', 'scripts/extract-zip.py'):
                with self.subTest(path=path), self.assertRaisesRegex(
                        ValueError, 'unsupported Whitaker source path'):
                    fetch_source('a' * 40, path)
            factory.assert_not_called()

    def test_transport_byte_and_elapsed_time_bounds(self):
        """Synthetic large/slow responses fail without running network requests."""
        for chunk, elapsed, message in [(b'x' * (128 * 1024 + 1), 0, 'size limit'),
                                        (b'x', 31, 'time budget')]:
            with self.subTest(bound=message), patch('whitaker_probe.urllib.request.build_opener') as factory:
                response = factory.return_value.open.return_value.__enter__.return_value
                response.read.side_effect = [chunk, b'']
                with patch('whitaker_probe.time.monotonic', side_effect=[0, elapsed]):
                    with self.assertRaisesRegex(ValueError, message):
                        fetch_manifest('a' * 40)

    def test_cli_fetches_only_the_manifest_at_the_actual_caller_ref(self):
        """The real CLI completes acquisition and probes using only fake transport."""
        seen = []
        prefix = ('https://raw.githubusercontent.com/leynos/shared-actions/' +
                  'b' * 40 + '/.github/actions/install-whitaker/')

        def response(url, timeout):
            """Return the manifest fixture for the one supported acquisition URL."""
            self.assertEqual(url, prefix + 'action.yml')
            self.assertEqual(timeout, 10)
            seen.append(url)
            return io.BytesIO(CAPABLE.encode())

        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / 'ci.yml'
            workflow.write_text(caller('b' * 40))
            with patch('whitaker_probe.urllib.request.build_opener') as factory, patch('sys.stdout', new_callable=io.StringIO) as output:
                factory.return_value.open.side_effect = response
                self.assertEqual(main(['--workflow', str(workflow)]), 0)
                self.assertIn('ref=' + 'b' * 40, output.getvalue())
                self.assertIn('scenarios=14', output.getvalue())
        self.assertEqual(seen, [prefix + 'action.yml'])
