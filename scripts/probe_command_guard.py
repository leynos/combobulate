"""Deny-by-default executors for probing untrusted command fragments.

A capability probe runs a source-derived shell fragment with synthetic inputs.
The stubs written here keep that fragment away from the host's network and
build tools: each denied name records that it was invoked, then exits with a
status the probe treats as a failed capability. They are a behavioural check,
not an operating-system sandbox.

The module deliberately holds no domain vocabulary. A probe-specific module
keeps its own tool names, so an audit that reads a whole script as command text
cannot mistake this generic refusal list for a route to a particular tool.
"""
from __future__ import annotations

import shlex
from pathlib import Path

DENIED_COMMANDS = ('curl', 'wget', 'git', 'cargo', 'rustup', 'python',
                   'python3', 'node', 'uv')
DENIED_COMMAND_MARKER = 'denied-command'
DENIED_EXIT_STATUS = 95
_DENIED_STUB = '''#!/bin/bash
printf '%s\\n' "$0" >> {marker}
exit {status}
'''


def write_executable(path: Path, source: str) -> None:
    """Write one private executable stub; e.g. a probe's fake installer."""
    path.write_text(source, encoding='utf-8')
    path.chmod(0o700)


def install_denied_commands(directory: Path, marker: Path) -> None:
    """Write refusal stubs that record invoked paths in ``marker`` and exit 95.

    The caller supplies the directory that receives one stub per entry in
    :data:`DENIED_COMMANDS`, and the marker file that records each attempted
    invocation. The stubs are an observability aid, not a sandbox.
    """
    source = _DENIED_STUB.format(
        marker=shlex.quote(str(marker)), status=DENIED_EXIT_STATUS)
    for command in DENIED_COMMANDS:
        write_executable(directory / command, source)