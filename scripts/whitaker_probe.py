#!/usr/bin/env python3
"""Resolve and behaviourally check the actual pinned Whitaker action before use.

Example: ``python scripts/whitaker_probe.py --workflow .github/workflows/ci.yml``.
The caller must pin the action to a full commit, which fixes the content the
probe fetches. Only manifest acquisition uses the network; capability probes use
private fake executors. The probes ask what the pinned action does, not whether
its files match a recorded digest, so a Dependabot bump passes whenever the
behaviour holds.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import yaml

from whitaker_capability import probe_manifest

ACTION_PATH = 'leynos/shared-actions/.github/actions/install-whitaker'
MANIFEST_PATH = 'action.yml'
MAX_MANIFEST_BYTES = 128 * 1024
NETWORK_TIMEOUT_SECONDS = 10
NETWORK_DEADLINE_SECONDS = 30


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


def _job_installer(job_name: str, job: object) -> str | None:
    """Resolve one job's Whitaker installer reference; e.g. None when it installs none."""
    steps = job.get('steps') if isinstance(job, dict) else None
    installers = [step for step in steps or [] if isinstance(step, dict)
                  and str(step.get('uses', '')).startswith(ACTION_PATH + '@')]
    if not installers:
        return None
    if len(installers) != 1:
        raise ValueError(f'{job_name} must contain exactly one Whitaker installer')
    return installers[0]['uses'].split('@', 1)[1]


def caller_reference(workflow: dict) -> str:
    """Resolve the installer reference every calling job shares, not a fixture pin.

    DL-03 puts the installer in more than one required job, and each of those
    must run the same reviewed action. Resolving the reference per job and
    requiring one distinct value is what keeps a second job from installing a
    different Whitaker build behind the checks.

    Examples
    --------
    A workflow whose two jobs both pin `a…40` returns that reference; one job
    pinning a different commit raises ValueError.
    """
    jobs = workflow['jobs']
    references = {reference for name, job in jobs.items()
                  if (reference := _job_installer(name, job)) is not None}
    if not references:
        raise ValueError('no job installs the Whitaker action')
    if len(references) != 1:
        raise ValueError('every job must install the same Whitaker reference')
    reference = references.pop()
    if not re.fullmatch('[0-9a-f]{40}', reference):
        raise ValueError('Whitaker must use a full lowercase hexadecimal commit SHA')
    return reference


class NoRedirects(urllib.request.HTTPRedirectHandler):
    """Keep acquisition on the exact HTTPS source URL, without redirect expansion."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        """Refuse redirection, e.g. to a different source host."""
        raise ValueError('manifest source redirected away from its exact URL')


def fetch_source(reference: str, path: str) -> str:
    """Fetch the composite manifest at the caller's exact immutable source ref."""
    if not re.fullmatch('[0-9a-f]{40}', reference):
        raise ValueError('invalid source reference')
    if path != MANIFEST_PATH:
        raise ValueError('unsupported Whitaker source path')
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
    return fetch_source(reference, MANIFEST_PATH)


def verify_workflow(source: str, fetcher: Callable[[str, str], str] = fetch_source) -> dict:
    """Bind behavioural evidence to the caller's full-commit pin of the action.

    The pin fixes the manifest content, so the digest below is provenance for a
    reviewer rather than a value compared against an expected one. Rejection
    comes from the probes observing behaviour the caller requires.
    """
    reference = caller_reference(document(source))
    manifest_source = fetcher(reference, MANIFEST_PATH)
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
