"""Read a Kani log into admission facts the evidence gate can check (VO-11).

The evidence gate must not believe a record that says a proof ran; it must read
the proof's own output. This package is the Kani half of that, split by what
each part needs to know:

- :mod:`~docs_validation.kani_log.syntax` names the grammar — the regular
  expressions, markers, and statuses a Kani log is read with.
- :mod:`~docs_validation.kani_log.model` holds the parsed value types, so a
  test can construct facts without a log and the walker can stay the only
  module that needs the grammar.
- :mod:`~docs_validation.kani_log.reader` consumes one report construct at a
  time, refusing any line inside a report the grammar does not account for.
- :mod:`~docs_validation.kani_log.extract` recognises the log's shape — banner,
  harness blocks, manual summary — and reconciles their counts.
- :mod:`~docs_validation.kani_log.manifest` turns the committed harness
  manifest into the roles, covers, and expected control failures a decision
  needs, without which a log cannot say what was meant to happen.
- :mod:`~docs_validation.kani_log.decide` is a pure function from those facts
  and the manifest to the admission facts VO-11b defines. It reads no files, so
  a decision can be re-derived from the same two inputs.

The split follows the execplan's planned module boundaries and keeps each
module testable on its own: the extractor over log text, the decision function
over constructed facts, and the shell adapter (which owns every read, digest,
and subprocess) outside both. It also keeps every module under the repository's
400-line limit, which a single extractor or a single decision module outgrew.

Examples
--------
>>> Manifest((Harness('h::x', 'claim'),)).names()
('h::x',)
>>> try:
...     parse('not a log')
... except KaniLogError as error:
...     print(error)
structural error: the log does not begin with a Kani banner
"""
from .decide import (
    ACCEPTED, BOUNDS, COUNTEREXAMPLE, FOCUSED, FULL_PROFILE, REJECTED_AS_INTENDED,
    REJECTED_OTHERWISE, RESOURCE_EXHAUSTED, SATISFIED, SKIPPED, SOLVER_UNKNOWN,
    TOOL_ERROR, UNSATISFIED, UNSUPPORTED, VERIFIED, Decision, decide, from_error,
)
from .extract import parse, unwinding_checks_enabled
from .manifest import CLAIM, CONTROL, ROLES, Harness, Manifest, manifest_from_document
from .model import HarnessBlock, KaniLog, ManualSummary
from .syntax import BANNER, SUPPORTED_VERSIONS, FailedCheck, KaniLogError, PropertyResult

__all__ = [
    'ACCEPTED', 'BANNER', 'BOUNDS', 'CLAIM', 'CONTROL', 'COUNTEREXAMPLE', 'FOCUSED', 'FULL_PROFILE',
    'REJECTED_AS_INTENDED', 'REJECTED_OTHERWISE', 'RESOURCE_EXHAUSTED', 'ROLES', 'SATISFIED',
    'SKIPPED', 'SOLVER_UNKNOWN', 'SUPPORTED_VERSIONS', 'TOOL_ERROR', 'UNSATISFIED', 'UNSUPPORTED',
    'VERIFIED', 'Decision', 'FailedCheck', 'Harness', 'HarnessBlock', 'KaniLog', 'KaniLogError',
    'Manifest', 'ManualSummary', 'PropertyResult', 'decide', 'from_error', 'manifest_from_document',
    'parse', 'unwinding_checks_enabled',
]
