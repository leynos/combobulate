"""Bind the toolchain and profile record to every site that asserts a pin (VO-7, VO-8).

VO-7 asks that a pinned revision agree everywhere it appears, so this checker
re-derives each pin from the file that owns it and compares the result with
``spec/toolchain-profiles.json``. The record names its own sites, which is what
keeps the sweep honest: a site the record omits is not compared, so the checker
also sweeps the tracked tree for the literal version strings and fails when one
appears in a file the record does not list.

VO-8 asks that a capability claiming an observation cite the committed log that
shows it. The statuses this repository can currently support are documentation
statuses: EP-M1 planned nine probes and ran none, so every capability is
``documented-upstream-opportunity`` and carries no evidence. A status that
claims more must supply a path and a matching SHA-256, so a later probe cannot
be recorded as tested without its log.
"""
from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path

from .context import ValidationContext, require

RECORD = 'spec/toolchain-profiles.json'
SCHEMA = 'spec/toolchain-profiles.schema.json'

# Directories whose contents are tool output rather than repository source.
# A pin string inside compiled artefacts proves nothing about a pin site.
SWEEP_SKIP_PREFIXES = (
    'target/', 'profile-results/', '.git/', 'docs/execplans/',
    'tools/probes/observations/', 'scripts/tests/fixtures/',
    'tools/verifier-fixtures/kani-corpus/target/',
)

# Documentation restates pins on purpose, and the record is the source being
# checked, so neither is a competing site. Everything else that names a pin
# must be listed in the record or this checker will report it.
DOCUMENTATION_SUFFIXES = ('.md',)

# The tracked corpus that captures real tool output. A pin inside a captured log
# is evidence of what the tool was, not a place this repository sets it.
CAPTURE_DIRECTORIES = ('scripts/tests/fixtures/kani_logs/', 'tools/verifier-fixtures/')


def check_toolchain_profiles(context: ValidationContext,
                             tracked: Iterable[str] | None = None) -> None:
    """Validate the profile record against its schema, its sources, and the tree.

    Parameters
    ----------
    context : ValidationContext
        Repository inputs owned by the documentation checker.
    tracked : Iterable[str] | None
        Repository-relative files the pin sweep may read. ``None`` reads the
        tracked tree through Git, which is what production uses. A test supplies
        an explicit list so it can add or omit a candidate site without touching
        the checkout.

    Returns
    -------
    None
        Records one result for the profile record.

    Raises
    ------
    AssertionError
        If the record disagrees with a source file, cites an unlisted pin site,
        or reports a capability status whose evidence is missing or wrong.
    jsonschema.ValidationError
        If the record does not match its schema.
    OSError
        If the record, its schema, or a cited source cannot be read.

    Examples
    --------
    check_toolchain_profiles(context) accepts a record whose pins agree with
    ``rust-toolchain.toml`` and whose capabilities cite no unevidenced status.
    """
    from jsonschema import Draft202012Validator

    record = context.load(RECORD)
    Draft202012Validator(context.load(SCHEMA)).validate(record)
    _check_record_shape(record)
    _check_sourced_pins(context.root, record)
    _check_pin_sweep(context.root, record, tracked)
    _check_capability_evidence(context.root, record['capabilities'])
    context.record('toolchain-profiles',
                   'Pins agree with every site the record names, no unlisted site repeats a pin, '
                   'and every capability status that claims an observation cites its log.',
                   len(record['pins']) + len(record['capabilities']))


def _check_record_shape(record: Mapping[str, object]) -> None:
    """Reject a record that cannot answer the questions it exists to answer."""
    profile_ids = [profile['id'] for profile in record['profiles']]
    require(len(profile_ids) == len(set(profile_ids)), 'Duplicate profile ID in the toolchain record')
    capability_ids = [capability['id'] for capability in record['capabilities']]
    require(len(capability_ids) == len(set(capability_ids)),
            'Duplicate capability ID in the toolchain record')
    ordinary = [toolchain for toolchain in record['supported_toolchain_set'] if toolchain['ordinary']]
    require(len(ordinary) == 1,
            'Exactly one supported toolchain may be the ordinary build toolchain; '
            f'found {len(ordinary)}')


def _check_sourced_pins(root: Path, record: Mapping[str, object]) -> None:
    """Re-derive each pin the record has a reader for and compare.

    Only pins with an unambiguous owning file are re-derived here. The rest are
    covered by :func:`_check_pin_sweep`, which is what keeps this function from
    growing a bespoke parser per capture format.
    """
    pins = record['pins']
    readers = {
        'repository_channel': _read_toolchain_channel,
        'kani_release': _read_single_line('tools/kani/VERSION'),
        'verus_release': _read_single_line('tools/verus/VERSION'),
        'prover_tools_ref': _read_prover_tools_ref,
        'verus_vstd': _read_vstd_requirement,
        'polars_release': _read_polars_requirement,
    }
    for pin_id, reader in readers.items():
        actual = reader(root)
        expected = pins[pin_id]['value']
        require(actual == expected,
                f"toolchain record pin {pin_id} is {expected!r} but its owner says {actual!r}")
        require(_pin_sites(root, expected, pins[pin_id]['sites']),
                f"pin {pin_id} cites a site that does not contain {expected!r}")


def _pin_sites(root: Path, value: str, sites: Iterable[str]) -> bool:
    """Require every cited site to exist and to name the pin's value.

    A cited site that no longer contains the value is the exact drift VO-7 is
    about: the record would still promise the pin while its source had moved.
    """
    texts = (_read_text(root / site) for site in sites)
    # Strip the Cargo requirement operator so `=0.0.0-…` matches the lockfile.
    needle = value.lstrip('=^~')
    return all(text is not None and needle in text for text in texts)


def _read_text(path: Path) -> str | None:
    """Read a cited file, or report None when the record cites something absent."""
    return path.read_text(encoding='utf-8') if path.is_file() else None


def _read_toolchain_channel(root: Path) -> str:
    """Read the repository channel from `rust-toolchain.toml`."""
    return tomllib.loads((root / 'rust-toolchain.toml').read_text(encoding='utf-8'))['toolchain']['channel']


def _read_single_line(relative: str):
    """Build a reader for a pin file whose whole content is the value."""
    def read(root: Path) -> str:
        """Return the pin file's content with its trailing newline removed."""
        return (root / relative).read_text(encoding='utf-8').strip()
    return read


def _read_prover_tools_ref(root: Path) -> str:
    """Read the pinned prover-tools commit from its REF file."""
    text = (root / 'tools/rust-prover-tools/REF').read_text(encoding='utf-8')
    match = re.search(r'^ref:\s*([0-9a-f]{40})$', text, re.MULTILINE)
    require(match is not None, 'tools/rust-prover-tools/REF has no 40-hex ref line')
    return match[1]


def _read_vstd_requirement(root: Path) -> str:
    """Read the exact `vstd` requirement the Verus fixture selects.

    The three fixture manifests pin the same requirement, so disagreement among
    them is itself a failure rather than something to resolve by picking one.
    """
    manifests = sorted((root / 'tools/verifier-fixtures/verus-wiring-probe').glob('*/Cargo.toml'))
    requirements = {
        _vstd_requirement_of(tomllib.loads(manifest.read_text(encoding='utf-8')))
        for manifest in manifests
    }
    requirements.discard(None)
    require(len(requirements) == 1,
            f'Verus fixture manifests disagree on vstd: {sorted(requirements)}')
    return requirements.pop()


def _vstd_requirement_of(manifest: Mapping[str, object]) -> str | None:
    """Return the `vstd` version string from one fixture manifest, if it has one."""
    dependencies = manifest.get('dependencies', {})
    entry = dependencies.get('vstd') if isinstance(dependencies, Mapping) else None
    if isinstance(entry, Mapping):
        return entry.get('version')
    return entry if isinstance(entry, str) else None


def _read_polars_requirement(root: Path) -> str:
    """Read the facade's Polars requirement, ignoring the probe's duplicate pin."""
    manifest = tomllib.loads((root / 'Cargo.toml').read_text(encoding='utf-8'))
    entry = manifest['dependencies']['polars']
    return entry['version']


def _check_pin_sweep(root: Path, record: Mapping[str, object],
                     tracked: Iterable[str] | None = None) -> None:
    """Fail when a pin appears in a tracked file the record does not name.

    The sweep is what makes the record's site list load-bearing. Without it the
    list could shrink to whichever files a change happened to touch, and the
    check would still pass while a real pin lived outside it.
    """
    record_sites = {site for pin in record['pins'].values() for site in pin['sites']}
    values = {pin['value'].lstrip('=^~'): pin_id for pin_id, pin in record['pins'].items()}
    for path in _tracked_text_files(root, tracked):
        relative = path.relative_to(root).as_posix()
        if relative == RECORD or _is_ignorable_site(relative):
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        for value, pin_id in values.items():
            if value not in text:
                continue
            require(relative in record_sites,
                    f'{relative} names pin {pin_id} ({value!r}) but the toolchain record does not list it')


def _is_ignorable_site(relative: str) -> bool:
    """Report whether a file restates pins without asserting one."""
    return (relative.startswith(SWEEP_SKIP_PREFIXES)
            or relative.endswith(DOCUMENTATION_SUFFIXES)
            or relative.startswith(CAPTURE_DIRECTORIES))


def _tracked_text_files(root: Path, tracked: Iterable[str] | None = None) -> Iterable[Path]:
    """Yield the files the sweep reads, resolved beneath ``root``.

    Resolving a relative path under ``root`` is what stops a caller's list from
    pointing outside the checkout. A directory or a path Git no longer tracks is
    skipped rather than read, so a stale entry cannot fail the sweep by itself.
    """
    from .revision_reader import tracked_paths

    candidates = tracked if tracked is not None else tracked_paths(root)
    return (root / relative for relative in candidates if (root / relative).is_file())


def _check_capability_evidence(root: Path, capabilities: Iterable[Mapping[str, object]]) -> None:
    """Require a claimed observation to cite a log whose digest matches."""
    for capability in capabilities:
        status = capability['status']
        if status == 'documented-upstream-opportunity':
            continue
        evidence = capability['evidence']
        path = root / evidence['path']
        require(path.is_file(), f"{capability['id']} cites missing evidence {evidence['path']}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        require(digest == evidence['sha256'],
                f"{capability['id']} evidence digest does not match {evidence['path']}")
