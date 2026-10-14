"""Hermetic source acquisition and caller-binding regressions for Whitaker CI."""
from __future__ import annotations

import hashlib
import json
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from whitaker_probe import NoRedirects, document, fetch_manifest, fetch_source, main, verify_workflow

FIXTURES = Path(__file__).parent / 'fixtures' / 'whitaker'
APPROVED = json.loads((FIXTURES / 'approved-source.json').read_text())
CAPABLE = APPROVED['action.yml']
LEGACY = (FIXTURES / 'legacy.yml').read_text()
ACTION = 'leynos/shared-actions/.github/actions/install-whitaker'


def caller(reference: str) -> str:
    """Build a workflow whose actual candidate ref is independent of fixture source."""
    return f'jobs:\n  build-test:\n    steps:\n      - uses: {ACTION}@{reference}\n'


class SourceBindingTests(unittest.TestCase):
    """A shape-valid SHA is accepted only after its own resolved source passes probes."""

    def test_same_capability_at_multiple_resolved_refs_passes(self):
        """A pin-only Dependabot bump needs no lockstep expected-SHA update."""
        candidates = {'a' * 40: CAPABLE, 'b' * 40: CAPABLE}
        seen = []
        for reference in candidates:
            def acquire(current, path):
                seen.append((current, path))
                return {**APPROVED, 'action.yml': candidates[current]}[path]
            evidence = verify_workflow(caller(reference), acquire)
            self.assertEqual(evidence['reference'], reference)
            self.assertEqual(evidence['manifest_sha256'], hashlib.sha256(CAPABLE.encode()).hexdigest())
            self.assertEqual(evidence['scenarios'], 12)
        self.assertEqual(seen, [(ref, path) for ref in candidates for path in APPROVED])

    def test_old_capability_is_rejected_despite_valid_sha_shape(self):
        """The upstream pre-#522 manifest cannot satisfy the binary-only obligation."""
        with self.assertRaisesRegex(ValueError, 'unapproved execution content: action.yml'):
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
        with self.assertRaisesRegex(ValueError, 'size limit'):
            verify_workflow(caller('a' * 40), lambda *_: 'x' * (128 * 1024 + 1))

    def test_complete_content_changes_reject_before_executing_probes(self):
        """Helpers, digest pins and manifest-only dependencies cannot evade approval."""
        for altered in APPROVED:
            with self.subTest(path=altered), patch('whitaker_probe.probe_manifest') as probe:
                def acquire(_, path):
                    return APPROVED[path] + ('\n# changed\n' if path == altered else '')
                with self.assertRaisesRegex(ValueError, f'unapproved execution content: {altered}'):
                    verify_workflow(caller('a' * 40), acquire)
                probe.assert_not_called()

    def test_missing_helper_fails_before_any_source_fragment_runs(self):
        """Every source path must exist at the actual ref; no vendored fallback is used."""
        with patch('whitaker_probe.probe_manifest') as probe:
            def acquire(_, path):
                if path == 'scripts/extract-zip.py':
                    raise OSError('helper unavailable')
                return APPROVED[path]
            with self.assertRaisesRegex(OSError, 'helper unavailable'):
                verify_workflow(caller('a' * 40), acquire)
            probe.assert_not_called()

    def test_fetch_uses_exact_pinned_url_and_timeout(self):
        """A fake response tests acquisition arguments without performing a request."""
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, _):
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

    def test_transport_refuses_redirects_and_unapproved_paths(self):
        """Neither a new host nor an unreviewed local helper can enter acquisition."""
        with self.assertRaisesRegex(ValueError, 'redirected'):
            NoRedirects().redirect_request(None, None, 302, '', {}, 'https://fixture.invalid')
        with patch('whitaker_probe.urllib.request.build_opener') as factory:
            with self.assertRaisesRegex(ValueError, 'outside the approved'):
                fetch_source('a' * 40, '../other-action/run.sh')
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

    def test_cli_fetches_every_approved_path_at_the_actual_caller_ref(self):
        """The real CLI completes acquisition and probes using only fake transport."""
        seen = []
        prefix = ('https://raw.githubusercontent.com/leynos/shared-actions/' +
                  'b' * 40 + '/.github/actions/install-whitaker/')
        def response(url, timeout):
            self.assertTrue(url.startswith(prefix))
            self.assertEqual(timeout, 10)
            path = url.removeprefix(prefix)
            seen.append(path)
            return io.BytesIO(APPROVED[path].encode())
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / 'ci.yml'
            workflow.write_text(caller('b' * 40))
            with patch('whitaker_probe.urllib.request.build_opener') as factory, patch('sys.stdout', new_callable=io.StringIO) as output:
                factory.return_value.open.side_effect = response
                self.assertEqual(main(['--workflow', str(workflow)]), 0)
                self.assertIn('ref=' + 'b' * 40, output.getvalue())
                self.assertIn('scenarios=12', output.getvalue())
        self.assertEqual(seen, list(APPROVED))
