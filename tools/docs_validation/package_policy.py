"""Keep the package manifest aligned with the accepted licence and publication policy.

D04 ratifies the ISC licence and D05 blocks crates.io publication until the
Core acceptance dossier passes and the sponsor approves release (ADR-0004).
The publication lock lifts only after an accepted D05 supersession and
validated task 4.3.3 closure are both present.
"""
from __future__ import annotations

import tomllib
from typing import TypedDict, cast

from .context import ValidationContext, require
from .roadmap_status import roadmap_tasks


class CargoPackageFields(TypedDict, total=False):
    """Cargo package fields consumed by the publication and licence policy."""

    license: str
    publish: bool | list[str]


class CargoManifest(TypedDict):
    """Typed projection of the Cargo manifest fields used by this checker."""

    package: CargoPackageFields


def check_manifest(manifest: CargoManifest, *, require_isc: bool = True,
                   require_unpublished: bool = True) -> None:
    """Validate the Cargo fields governed by accepted package decisions.

    Parameters
    ----------
    manifest
        Parsed Cargo manifest, viewed through the package fields this policy
        reads. Other Cargo fields remain outside this check.
    require_isc
        Require the package licence to be ``ISC`` while D04 stands.
    require_unpublished
        Require ``publish = false`` while D05 stands or its release conditions
        have not both been validated.

    Raises
    ------
    AssertionError
        If a required package field does not match the accepted policy.

    Examples
    --------
    An ISC package that is not publishable satisfies both requirements::

        manifest = {'package': {'license': 'ISC', 'publish': False}}
        check_manifest(manifest)
    """
    package = manifest['package']
    if require_isc:
        require(package.get('license') == 'ISC', 'Cargo.toml must declare license = "ISC" (D04)')
    if require_unpublished:
        require(package.get('publish') is False,
                'Cargo.toml must set publish = false until task 4.3.3 passes and release is approved (D05)')


def _has_accepted_d05_supersession(decisions: dict[str, dict]) -> bool:
    """Report whether an accepted decision directly supersedes D05.

    For example, an accepted replacement linked from D05 records sponsor
    approval to change the publication policy::

        decisions = {
            'D05': {'lifecycle': 'superseded', 'superseded_by': 'D16'},
            'D16': {'lifecycle': 'accepted', 'supersedes': ['D05']},
        }
        _has_accepted_d05_supersession(decisions)
        # True
    """
    d05 = decisions.get('D05')
    if d05 is None or d05.get('lifecycle') != 'superseded':
        return False
    replacement = decisions.get(d05.get('superseded_by'))
    return (replacement is not None and replacement.get('lifecycle') == 'accepted'
            and 'D05' in replacement.get('supersedes', []))


def _has_validated_core_dossier(context: ValidationContext) -> bool:
    """Require a completed 4.3.3 record backed by the successful closure check.

    The package check runs after ``check_roadmap_status`` in the composition.
    That check validates the task's prerequisites, decisions, artefacts, and
    proof-obligation components before recording its successful result.

    Examples
    --------
    A successful roadmap closure result is required before package publication
    can be enabled::

        from pathlib import Path

        context = ValidationContext(Path.cwd())
        _has_validated_core_dossier(context)
        # False until task 4.3.3 is ticked and validated
    """
    roadmap_passed = any(row.get('check') == 'roadmap-status' and row.get('status') == 'pass'
                         for row in context.results)
    if not roadmap_passed:
        return False
    task = roadmap_tasks(context.load('spec/roadmap.json')).get('4.3.3')
    completion_records = context.load('spec/task-completion.json')['tasks']
    has_completion_record = any(record['task'] == '4.3.3' for record in completion_records)
    return task is not None and task['status'] == 'done' and has_completion_record


def check_package_policy(context: ValidationContext) -> None:
    """Apply accepted licence and publication decisions to ``Cargo.toml``.

    Parameters
    ----------
    context
        Repository validation context. A successful ``roadmap-status`` result
        and a completed task 4.3.3 record are required before an accepted D05
        supersession can lift the publication guard.

    Examples
    --------
    From the repository root, the checker records the package-policy result::

        from pathlib import Path

        context = ValidationContext(Path.cwd())
        check_package_policy(context)
        context.results[-1]['check']
        # 'package-policy'
    """
    decisions = {record['id']: record for record in context.load('spec/decisions.json')['decisions']}
    release_conditions_met = (_has_accepted_d05_supersession(decisions)
                              and _has_validated_core_dossier(context))
    require_unpublished = not release_conditions_met
    manifest = cast(CargoManifest, tomllib.loads((context.root / 'Cargo.toml').read_text(encoding='utf-8')))
    check_manifest(manifest, require_isc=decisions.get('D04', {}).get('lifecycle') == 'accepted',
                   require_unpublished=require_unpublished)
    context.record('package-policy', 'Cargo.toml meets the D04 licence policy and keeps publication disabled until '
                                      'an accepted D05 supersession and validated task 4.3.3 closure.', 1)
