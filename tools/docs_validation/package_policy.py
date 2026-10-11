"""Keep the package manifest aligned with the accepted licence and publication policy.

D04 ratifies the ISC licence and D05 blocks crates.io publication until the
Core acceptance dossier passes and the sponsor approves release (ADR-0004).
While each decision stands accepted, the manifest must agree with it; a
superseding decision that approves release lifts the publication rule.
"""
from __future__ import annotations

import tomllib

from .context import ValidationContext, require


def check_manifest(manifest: dict, *, require_isc: bool = True, require_unpublished: bool = True) -> None:
    """Check one parsed manifest; e.g. a package without ``publish = false`` fails under D05."""
    package = manifest['package']
    if require_isc:
        require(package.get('license') == 'ISC', 'Cargo.toml must declare license = "ISC" (D04)')
    if require_unpublished:
        require(package.get('publish') is False, 'Cargo.toml must set publish = false until release is approved (D05)')


def check_package_policy(context: ValidationContext) -> None:
    """Apply each accepted package decision to the committed `Cargo.toml`."""
    lifecycle = {record['id']: record['lifecycle'] for record in context.load('spec/decisions.json')['decisions']}
    manifest = tomllib.loads((context.root / 'Cargo.toml').read_text(encoding='utf-8'))
    rules = {'D04': 'the ISC licence', 'D05': 'publish = false'}
    active = {decision: rule for decision, rule in rules.items() if lifecycle.get(decision) == 'accepted'}
    check_manifest(manifest, require_isc='D04' in active, require_unpublished='D05' in active)
    enforced = '; '.join(f'{rule} ({decision})' for decision, rule in active.items()) or 'no package rule'
    context.record('package-policy', f'Cargo.toml satisfies the accepted package decisions: {enforced}.', len(active))
