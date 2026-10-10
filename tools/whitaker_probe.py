#!/usr/bin/env python3
"""Resolve and behaviourally check the actual pinned Whitaker action before use.

Example: ``python tools/whitaker_probe.py --workflow .github/workflows/ci.yml``.
Only approved-source acquisition uses the network; capability probes use private
fake executors. Complete content approval precedes the selected boundary probes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import yaml

from whitaker_capability import probe_manifest

ACTION_PATH = 'leynos/shared-actions/.github/actions/install-whitaker'
MAX_MANIFEST_BYTES = 128 * 1024
NETWORK_TIMEOUT_SECONDS = 10
NETWORK_DEADLINE_SECONDS = 30
APPROVAL = Path(__file__).with_name('whitaker-approved.json')


class UniqueSafeLoader(yaml.SafeLoader):
    """Reject duplicate mappings while retaining PyYAML's safe constructors."""

    def construct_mapping(self, node, deep=False):
        """Reject duplicate keys, e.g. a hidden replacement run fragment."""
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if any(keys.count(key) != 1 for key in keys):
            raise ValueError('duplicate YAML mapping keys')
        return super().construct_mapping(node, deep=deep)


def document(source: str) -> dict:
    """Parse bounded safe YAML; e.g. a scalar manifest is rejected."""
    if len(source.encode('utf-8')) > MAX_MANIFEST_BYTES:
        raise ValueError('manifest exceeds the source size limit')
    result = yaml.load(source, Loader=UniqueSafeLoader)
    if not isinstance(result, dict):
        raise ValueError('workflow/action must be a mapping')
    return result


def caller_reference(workflow: dict) -> str:
    """Resolve the single build-test installer reference, rather than a fixture pin."""
    steps = workflow['jobs']['build-test']['steps']
    installers = [step for step in steps if isinstance(step, dict)
                  and str(step.get('uses', '')).startswith(ACTION_PATH + '@')]
    if len(installers) != 1:
        raise ValueError('build-test must contain exactly one Whitaker installer')
    reference = installers[0]['uses'].split('@', 1)[1]
    if not re.fullmatch('[0-9a-f]{40}', reference):
        raise ValueError('Whitaker must use a full lowercase hexadecimal commit SHA')
    return reference


class NoRedirects(urllib.request.HTTPRedirectHandler):
    """Keep acquisition on the exact HTTPS source URL, without redirect expansion."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        """Refuse redirection, e.g. to a different source host."""
        raise ValueError('manifest source redirected away from its exact URL')


def fetch_source(reference: str, path: str) -> str:
    """Fetch an approved relative path at the caller's exact immutable source ref."""
    if not re.fullmatch('[0-9a-f]{40}', reference):
        raise ValueError('invalid source reference')
    if path not in json.loads(APPROVAL.read_text())['files']:
        raise ValueError('source path is outside the approved execution set')
    url = ('https://raw.githubusercontent.com/leynos/shared-actions/'
           f'{reference}/.github/actions/install-whitaker/{path}')
    opener = urllib.request.build_opener(NoRedirects())
    started = time.monotonic()
    chunks = []
    total = 0
    with opener.open(url, timeout=NETWORK_TIMEOUT_SECONDS) as response:
        while chunk := response.read(8192):
            total += len(chunk)
            if total > MAX_MANIFEST_BYTES:
                raise ValueError('downloaded manifest exceeds the source size limit')
            if time.monotonic() - started > NETWORK_DEADLINE_SECONDS:
                raise ValueError('manifest acquisition exceeded its time budget')
            chunks.append(chunk)
    return b''.join(chunks).decode('utf-8')


def fetch_manifest(reference: str) -> str:
    """Acquire the full composite manifest, e.g. for a diagnostic source read."""
    return fetch_source(reference, 'action.yml')


def approved_manifest(reference: str, fetcher: Callable[[str, str], str]) -> str:
    """Authenticate the complete execution set before any source-derived code runs.

    Identical reviewed content at a new commit is valid. Changed helpers, nested
    action refs, digests or shell steps require an explicit evidence-map update.
    """
    approval = json.loads(APPROVAL.read_text(encoding='utf-8'))
    sources = {}
    for path, expected in approval['files'].items():
        content = fetcher(reference, path)
        if len(content.encode('utf-8')) > MAX_MANIFEST_BYTES:
            raise ValueError('approved source exceeds the source size limit')
        digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
        if digest != expected:
            raise ValueError(f'unapproved execution content: {path}')
        sources[path] = content
    return sources['action.yml']


def verify_workflow(source: str, fetcher: Callable[[str, str], str] = fetch_source) -> dict:
    """Bind content approval and behavioural evidence to the actual caller ref."""
    reference = caller_reference(document(source))
    manifest_source = approved_manifest(reference, fetcher)
    manifest = document(manifest_source)
    scenarios = probe_manifest(manifest)
    return {'reference': reference, 'manifest_sha256': hashlib.sha256(
        manifest_source.encode('utf-8')).hexdigest(), 'scenarios': scenarios}


def main(argv: list[str] | None = None) -> int:
    """Fail closed on unavailable source or failed probes, with reviewable provenance."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workflow', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        evidence = verify_workflow(args.workflow.read_text(encoding='utf-8'))
    except (ValueError, KeyError, TypeError, OSError, yaml.YAMLError) as error:
        parser.exit(1, f'Whitaker capability check failed: {error}\n')
    print('Whitaker capability checked: '
          f"ref={evidence['reference']} manifest-sha256={evidence['manifest_sha256']} "
          f"scenarios={evidence['scenarios']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
