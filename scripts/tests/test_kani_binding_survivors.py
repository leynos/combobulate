"""Kill the decision and binding mutants a corpus sweep leaves alive (VO-11b, VO-12).

The mutation census over :mod:`docs_validation.kani_log` leaves survivors where
the mutation changes a *reported* fact rather than an admission outcome: a
decision's ``reason``, a control's disposition detail, the label a refusal uses
for a nameless record, or the target of the editor line the refusal came from.
They survive because the existing suites assert outcomes, not the prose and
labels a record's author reads back.

Four families of survivor are equivalents rather than gaps, and this module
records why instead of silencing them: ``MissingEvidence`` is returned for a
refusal whose *label* the scanner does not compare, so a mutant that changed
one refusal's class still refuses; ``_manifest_sources``'s ``()`` and
omitted-argument defaults are unobservable because ``None`` is not a
``Sequence`` and so returns the same empty tuple — its own cases live in
``test_kani_manifest_source_list``; the ``(control.expected_failure or '')``
default in :func:`~docs_validation.kani_log.decide._rejected_as_intended` is
equivalent for a subtler reason: ``Harness.__post_init__`` refuses every falsy
expectation, and ``'   '`` is truthy, so the ``or`` never fires and the
``'XXXX'`` mutant cannot be reached; and ``bind_verdict``'s decoding of the log
is the last, where ``decode(errors='replace')`` and ``decode('UTF-8', ...)`` are
the same call as ``decode('utf-8', ...)``, because Python resolves the encoding
name case-insensitively and this host's preferred encoding is UTF-8. A mutant no
input can distinguish is not a gap.

``tracked_paths``'s ``check=False`` was reported as a fifth family and is *not*
one: ``check=True`` raises ``CalledProcessError`` where the function promises an
empty set, and ``test_a_repository_that_is_not_one_yields_no_paths`` requires
that empty set for a directory that is not a repository. The argument is
observable, so no test here claims otherwise.

Examples
--------
>>> unnamed_label()
'record'
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kani_decision_fixtures as facts
from docs_validation.kani_log import (
    CLAIM, CONTROL, Harness, Manifest, PropertyResult, decide, manifest_from_document,
)
from docs_validation.kani_log.decide import _Observed, _rejected_as_intended
from docs_validation.kani_log.shell import (
    GitUnavailable, MissingEvidence, UNNAMED_RECORD, bind_verdict, bound_sources,
    read_tracked, tracked_paths,
)
from git_fixtures import run_git
from kani_binding_fixtures import ROOT, ScratchCheckout, digest, record


def unnamed_label() -> str:
    """Return the label ``bind_verdict`` uses for a record whose ``id`` key is absent.

    The fallback is ``record.get('id', UNNAMED_RECORD)``, so it fires only when
    the key is missing; a record carrying ``id: null`` reaches the branch with
    the string ``'None'`` instead.
    """
    document = record(**{'verdict_source': 'log-parser'})
    del document['id']
    missing = bind_verdict(ROOT, document)
    if not isinstance(missing, MissingEvidence):
        raise AssertionError(f'the record should have refused, but bound {missing!r}')
    return missing.path


class RawByteCheckout:
    """A checkout whose log may hold bytes that are not valid UTF-8.

    The shared checkout writes its files from text, so it cannot express a log
    a producer wrote with a stray byte. The decode policy is only observable
    there: a replaced byte becomes ``U+FFFD`` and the log still parses, whereas
    strict decoding refuses it outright.

    The manifest may be replaced as well, because the shared checkout can only
    write one that the readers accept. A manifest that parses as JSON but
    declares an invalid harness is the sole input reaching the verdict
    adapter's own manifest refusal, since everything earlier refuses in a
    reader both callers share.
    """

    def __init__(self, log_bytes: bytes, manifest: str | None = None) -> None:
        """Create the checkout and commit the log, and either manifest, as given."""
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.root.joinpath('run.log').write_bytes(log_bytes)
        if manifest is None:
            manifest = (ROOT / 'scripts/tests/fixtures/evidence/default-unwind-manifest.json').read_text(
                encoding='utf-8')
        self.root.joinpath('manifest.json').write_text(manifest, encoding='utf-8')
        run_git(self.root, 'init', '-q')
        run_git(self.root, 'add', '-A')
        run_git(self.root, 'commit', '-q', '-m', 'Create raw byte fixture')

    def close(self) -> None:
        """Remove the checkout."""
        self._directory.cleanup()

    def record(self) -> dict:
        """Return a record binding this checkout's log and manifest by digest."""
        return record(
            verdict_source={'kind': 'log-parser',
                            'log': {'path': 'run.log',
                                    'sha256': digest(self.root.joinpath('run.log').read_bytes())}},
            result_artefacts=[{'path': 'manifest.json',
                               'sha256': digest(self.root.joinpath('manifest.json').read_bytes())}])


class DecisionReason(unittest.TestCase):
    """Require the decision to report the reason it was reached, not just its outcome."""

    def test_a_parsed_log_says_which_decision_was_taken(self):
        """Require the success reason, which is the only trace of *how* the decision ran.

        The gate compares the outcome, the bounds, and the run mode with the
        record; the reason is what a reader sees when those match but the prose
        does not. A mutant that replaced it with ``None``, upper-cased it, or
        dropped it would leave every outcome assertion intact.
        """
        decision = facts.decision_for((facts.HarnessFact('h::c', facts.CLAIM, facts.SUCCESS),))
        self.assertEqual(decision.reason, 'decided from the parsed log',
                         'a parsed decision must state the reason it was reached')


class WhitespaceExpectation(unittest.TestCase):
    """Require a whitespace-only expectation to match nothing, not any short string.

    ``Harness.__post_init__`` refuses a control whose ``expected_failure`` is
    empty or ``None``, but a manifest may still carry whitespace, which strips
    to the empty string. An empty expected value must then match no check: a
    mutant that substituted a placeholder string would instead accept any check
    whose identifier or kind happened to contain it, reporting a rejection the
    control never demonstrated.
    """

    def test_a_whitespace_expectation_matches_no_check(self):
        """Require whitespace to strip to nothing, which then contains no identifier.

        ``Harness.__post_init__`` refuses an empty or ``None`` expectation but
        admits whitespace, and stripping turns it into the empty string. An
        empty expectation is what the strip exists for: without it a manifest
        could blank out the control's declaration and still name a match.
        """
        control = Harness('h::k', CONTROL, (), '   ')
        seen = _Observed(name='h::k', succeeded=False, properties=(
            PropertyResult('h::k.assertion.1', 'FAILURE', 'an unrelated check fails'),
        ))
        self.assertFalse(_rejected_as_intended(control, seen),
                         'a whitespace expectation must not match an unrelated failure')

    def test_an_explicit_expectation_matches_its_check(self):
        """Require the positive case, so the whitespace case is not vacuously false."""
        control = Harness('h::k', CONTROL, (), 'assertion.1')
        seen = _Observed(name='h::k', succeeded=False, properties=(
            PropertyResult('h::k.assertion.1', 'FAILURE', 'the seeded fault fires'),
        ))
        self.assertTrue(_rejected_as_intended(control, seen),
                        'an expectation naming the failed check must match it')


class ControlDispositions(unittest.TestCase):
    """Require each control disposition to be distinguished from the others."""

    def test_a_control_that_failed_an_unexpected_property_is_rejected_otherwise(self):
        """Require the disposition detail, which separates a real control from a lucky one.

        A control declared ``assertion.1`` that instead failed ``assertion.2``
        must not count as rejected-as-intended: the seeded fault tripped an
        unrelated check, so the run has not shown the claim would be caught.
        """
        decision = facts.decision_for((
            facts.HarnessFact('h::c', facts.CLAIM, facts.SUCCESS),
            facts.HarnessFact('h::k', facts.CONTROL, facts.FAILURE, expected=facts.OTHERWISE),
        ))
        self.assertEqual(decision.negative_controls, ((True, 'rejected-otherwise'),),
                         'a control failing the wrong property must be rejected otherwise')

    def test_a_control_that_failed_its_own_property_is_rejected_as_intended(self):
        """Require the intended disposition, so the pair is not merely both-otherwise."""
        decision = facts.decision_for((
            facts.HarnessFact('h::c', facts.CLAIM, facts.SUCCESS),
            facts.HarnessFact('h::k', facts.CONTROL, facts.FAILURE, expected=facts.AS_INTENDED),
        ))
        self.assertEqual(decision.negative_controls, ((True, 'rejected-as-intended'),),
                         'a control failing its declared property must be rejected as intended')

    def test_a_control_that_did_not_fail_at_all_is_accepted(self):
        """Require the success flag, which is the only thing separating accepted from rejected.

        A control that reports SUCCESSFUL never tripped its seeded fault, so the
        run has shown nothing about the claim and the gate must report it as
        accepted. A mutant that stored ``None`` in place of the block's
        success would fall through to the failure branches and report a
        rejection that never happened.
        """
        decision = facts.decision_for((
            facts.HarnessFact('h::c', facts.CLAIM, facts.SUCCESS),
            facts.HarnessFact('h::k', facts.CONTROL, facts.SUCCESS, expected=facts.AS_INTENDED),
        ))
        self.assertEqual(decision.negative_controls, ((True, 'accepted'),),
                         'a control that did not fail must be reported as accepted')


class RefusalLabels(unittest.TestCase):
    """Require every refusal to name what a record's author has to fix."""

    def test_a_record_without_an_id_is_labelled(self):
        """Require the shared label, which three refusal sites rely on.

        A record with no id still has to be findable in a gate's output. The
        label is a named constant precisely so a mutant that substituted
        ``None`` or dropped it cannot leave a line beginning at the class.
        """
        self.assertEqual(unnamed_label(), UNNAMED_RECORD,
                         'a record with no id must be labelled by the shared constant')

    def test_a_tampered_manifest_still_refuses_when_its_label_changes(self):
        """Record the equivalence: the label is not compared, only the refusal is.

        The scanner and the gate both ask *whether* binding failed. This case
        exists so the next reader does not mistake the surviving label mutants
        for a missing assertion; the refusal itself is what is tested.
        """
        checkout = ScratchCheckout(manifest='[]')
        self.addCleanup(checkout.close)
        self.assertIsNotNone(bind_verdict(checkout.root, checkout.record()),
                             'a manifest that is not an object must refuse')

    def test_a_malformed_manifest_names_the_file_it_could_not_read(self):
        """Require the manifest path in the shape refusal, so the author has a file to open.

        The scanner re-parses the manifest before auditing its sources. A
        refusal that reported ``None`` in place of the path would still refuse,
        but the line would name no file the author could check.
        """
        checkout = ScratchCheckout(manifest='[]')
        self.addCleanup(checkout.close)
        missing = bound_sources(checkout.root, checkout.record())
        self.assertIsInstance(missing, MissingEvidence,
                              'a manifest that is not an object must refuse')
        self.assertEqual(missing.path, 'manifest.json',
                         'the refusal must name the manifest it could not read')

    def test_the_scan_binds_the_manifest_the_record_names(self):
        """Require the scanner to read the record's own manifest, not a placeholder.

        ``bound_sources`` re-opens the manifest the record cites, so its
        declared source list is what the scanner audits. A mutant that passed a
        literal path would audit the wrong file or refuse a valid record.

        The crate manifest leads the list because the audit reads it to decide
        whether the crate's literals are code, so it is bound with the sources
        that decision applies to.
        """
        sources = bound_sources(ROOT, record())
        self.assertEqual(tuple(sources),
                         ('tools/verifier-fixtures/kani-corpus/Cargo.toml',
                          'tools/verifier-fixtures/kani-corpus/src/lib.rs',
                          'tools/verifier-fixtures/kani-corpus/src/harnesses.rs'),
                         'the scanner must audit the sources the record manifest names')

    def test_the_bound_source_map_carries_the_bytes_the_digest_checked(self):
        """Require the verified text itself, not a path the scanner would re-open.

        Returning paths let the audit re-read each file, so the bytes it scanned
        were whatever the file held at that moment rather than the bytes whose
        digest :func:`bound_sources` had just accepted. Carrying the bytes makes
        the audited text and the verified text the same fact.
        """
        sources = bound_sources(ROOT, record())
        on_disk = (ROOT / 'tools/verifier-fixtures/kani-corpus/src/lib.rs').read_bytes()
        self.assertEqual(sources['tools/verifier-fixtures/kani-corpus/src/lib.rs'], on_disk,
                         'the bound bytes must be the file the digest was checked against')


class ManifestDefaults(unittest.TestCase):
    """Require the ``should_panic`` default to be the boolean false, not a falsy value.

    ``manifest_from_document`` now refuses anything but a JSON boolean, which
    makes the default observable: a default of ``()`` or ``None`` would be
    refused rather than read as "no panic expected". An omitted key must still
    mean false, because most manifest entries do not mention the flag.
    """

    def test_an_entry_without_should_panic_is_false(self):
        """Require the omitted flag to mean false, rather than to be refused."""
        document = {'harnesses': [{'name': 'h::x', 'role': 'claim'}]}
        self.assertFalse(manifest_from_document(document).harnesses[0].should_panic,
                         'an entry that omits should_panic must not declare it')

    def test_a_should_panic_that_is_not_a_boolean_is_refused(self):
        """Require a quoted or numeric flag to be refused rather than coerced."""
        for value in ('false', 'true', 1, 0, None):
            with self.subTest(value=value):
                document = {'harnesses': [{'name': 'h::x', 'role': 'claim',
                                           'should_panic': value}]}
                with self.assertRaises(ValueError,
                                       msg=f'{value!r} is not a JSON boolean and must be refused'):
                    manifest_from_document(document)


class ManifestRefusalLabel(unittest.TestCase):
    """Require the verdict adapter's manifest refusal to name its class and file.

    The adapter and the scanner refuse a malformed manifest through different
    calls, so each has its own label to get right. The scanner's is asserted in
    :mod:`test_kani_binding_scanner_refusals`; this is the adapter's, which is
    reached only by a manifest that parses as JSON but describes an invalid
    harness, because everything earlier refuses in a shared reader.
    """

    def missing(self) -> MissingEvidence:
        """Return the refusal this checkout produced, failing if it bound instead."""
        log = (ROOT / 'scripts/tests/fixtures/kani_logs/verified.log').read_bytes()
        checkout = RawByteCheckout(log, manifest='{"harnesses": [{"name": "h::x", "role": "nonsense"}]}')
        self.addCleanup(checkout.close)
        missing = bind_verdict(checkout.root, checkout.record())
        self.assertIsInstance(missing, MissingEvidence,
                              'a manifest naming an unknown role must refuse')
        return missing

    def test_a_malformed_manifest_is_refused_as_a_manifest(self):
        """Require the class, so the line tells a reader which artefact to open."""
        missing = self.missing()
        self.assertEqual(missing.what, 'manifest',
                         'the adapter must report the refusal against the manifest class')

    def test_the_refusal_names_the_manifest_file(self):
        """Require the path, without which the class alone does not locate the fault."""
        self.assertEqual(self.missing().path, 'manifest.json',
                         'the refusal must name the manifest that could not be read')

    def test_the_refusal_carries_the_manifests_own_reason(self):
        """Require the ``ValueError`` text, which names the harness and the role."""
        missing = self.missing()
        self.assertIn("unknown role 'nonsense'", missing.reason,
                      'the refusal must carry the reason the manifest gave')


class LogDecoding(unittest.TestCase):
    """Require a log with bytes that are not valid UTF-8 to be read, not to crash.

    A producer's log carries toolchain output, and a stray byte in a path or a
    test name must not turn a bindable log into an unhandled exception. The
    parser is fed the decoded text, so the policy lives in one call; these cases
    pin the policy itself rather than any refusal the parser raised.
    """

    def checkout(self, log_bytes: bytes) -> RawByteCheckout:
        """Create one raw-byte checkout and register its removal."""
        checkout = RawByteCheckout(log_bytes)
        self.addCleanup(checkout.close)
        return checkout

    def test_a_stray_trailing_byte_does_not_stop_the_verdict_being_bound(self):
        """Require the byte to be replaced, so the log still parses to its own verdict.

        Decoding strictly would raise ``UnicodeDecodeError`` out of
        ``bind_verdict``, which is not a ``MissingEvidence`` and so is not a
        refusal the gate can report: the whole run would fail instead.
        """
        log = (ROOT / 'scripts/tests/fixtures/kani_logs/verified.log').read_bytes()
        checkout = self.checkout(log + b'\xff\xfe\n')
        result = bind_verdict(checkout.root, checkout.record())
        self.assertNotIsInstance(result, MissingEvidence,
                                 'a log with a stray trailing byte must still bind')


class TrackedPathListings(unittest.TestCase):
    """Require ``tracked_paths`` to ask Git for the paths rather than for options."""

    def test_a_path_beginning_with_a_dash_is_listed_as_a_path(self):
        """Require the ``--`` separator, without which Git reads a path as a switch.

        A manifest may name a file such as ``-n``. Without the separator Git
        parses it as the ``--named``-style option it resembles and exits
        non-zero, so the file would be reported untracked although it is.
        """
        checkout = ScratchCheckout()
        self.addCleanup(checkout.close)
        self.root_dashed(checkout, '-n')
        self.assertEqual(tracked_paths(checkout.root, ['-n']), frozenset({'-n'}),
                         'a path beginning with a dash must be listed as a path')

    def root_dashed(self, checkout: ScratchCheckout, name: str) -> None:
        """Commit ``name`` in the checkout, which the shared constructor cannot express."""
        checkout.root.joinpath(name).write_text('fn main() {}\n', encoding='utf-8')
        run_git(checkout.root, 'add', '--', name)
        run_git(checkout.root, 'commit', '-q', '-m', 'Add a dash-leading source')

    def test_a_repository_that_is_not_one_yields_no_paths(self):
        """Require ``check=False``, since Git exits non-zero outside a repository.

        ``subprocess.run`` with ``check=True`` raises ``CalledProcessError``
        from inside the gate. The wrong root is exactly what the function is
        asked about, so it must answer rather than throw — and the answer must
        be that Git could not report, not that nothing is tracked. The two
        differ: the second would blame every cited path individually for a
        problem with the checkout.
        """
        with tempfile.TemporaryDirectory() as directory:
            result = tracked_paths(Path(directory), ['x'])
            self.assertIsInstance(result, GitUnavailable,
                                  'a directory that is not a repository must report why Git could not answer')
            self.assertTrue(result.detail,
                            'the report names what Git said, so the caller can print it')

    def test_a_read_from_a_non_repository_says_git_could_not_report(self):
        """Carry the Git failure into the read API's refusal rather than blaming the path."""
        with tempfile.TemporaryDirectory() as directory:
            result = read_tracked(Path(directory), 'run.log')
            self.assertIsInstance(result, MissingEvidence,
                                  'an unreadable checkout is still a refusal')
            self.assertIn('Git could not report', result.reason,
                          'the refusal names the real cause, not an untracked path')


if __name__ == '__main__':
    unittest.main()
