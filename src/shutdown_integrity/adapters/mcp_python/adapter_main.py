"""Adapter subprocess for mcp-py/rejected-connect-leaks-transport.

Speaks the wire protocol documented in shutdown_integrity.adapter over stdin
and stdout. Runs under one persistent event loop for the whole process
lifetime (`anyio.run(_serve)`) rather than one loop per op, because the
ClientSessionGroup it drives is an async context manager whose state (open
transports, task groups) cannot survive being entered and exited across
different event loops.

Derived from suts/mcp-python-sdk's own documented usage: connecting multiple
stdio servers through ClientSessionGroup (docs_src/session_groups/tutorial003.py)
is exactly the call sequence issue 3490 sits in.

Usage: <fixture-python> adapter_main.py, fed newline-delimited JSON on stdin.

start_session spec for this scenario:
    {
        "accepted_server": {"command": "...", "args": [...]},
        "rejected_server": {"command": "...", "args": [...]}
    }
Connects accepted_server first (must succeed), then rejected_server, whose
tool name is expected to collide and raise MCPError. That raise is the
contract boundary this scenario measures, not a separate teardown call: the
reply carries `rejected_as_expected` and `returned_after_s` covering exactly
the connect_to_server call that raised.
"""

import contextlib
import json
import os
import sys
import time
import uuid

import anyio

from mcp import ClientSessionGroup, StdioServerParameters
from mcp.shared.exceptions import MCPError

_TRIAL_TAG_ENV = "SHUTDOWN_INTEGRITY_TRIAL"
_ROLE_ENV = "SHUTDOWN_INTEGRITY_ROLE"


def _server_env(role: str) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", ""), _ROLE_ENV: role}
    trial_tag = os.environ.get(_TRIAL_TAG_ENV)
    if trial_tag is not None:
        env[_TRIAL_TAG_ENV] = trial_tag
    return env


def _server_params(spec: dict[str, object], role: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=spec["command"],  # type: ignore[arg-type]
        args=spec["args"],  # type: ignore[arg-type]
        env=_server_env(role),
    )


class _Sessions:
    """Live ClientSessionGroup objects keyed by handle, for this adapter's lifetime."""

    def __init__(self) -> None:
        self._groups: dict[str, ClientSessionGroup] = {}

    def put(self, handle: str, group: ClientSessionGroup) -> None:
        self._groups[handle] = group

    def get(self, handle: str) -> ClientSessionGroup:
        return self._groups[handle]

    def pop(self, handle: str) -> ClientSessionGroup:
        return self._groups.pop(handle)


async def _op_start_session(req: dict[str, object], sessions: _Sessions) -> dict[str, object]:
    """Per the wire protocol, the adapter assigns the handle; the caller does
    not supply one.
    """
    spec = req["spec"]  # type: ignore[assignment]
    assert isinstance(spec, dict)
    handle = uuid.uuid4().hex

    group = ClientSessionGroup()
    await group.__aenter__()
    sessions.put(handle, group)

    accepted_params = _server_params(spec["accepted_server"], "accepted")  # type: ignore[arg-type]
    rejected_params = _server_params(spec["rejected_server"], "rejected")  # type: ignore[arg-type]

    await group.connect_to_server(accepted_params)

    t0 = time.monotonic()
    rejected_as_expected = False
    rejection_error: str | None = None
    try:
        await group.connect_to_server(rejected_params)
    except MCPError as exc:
        rejected_as_expected = True
        rejection_error = str(exc)
    returned_after_s = time.monotonic() - t0

    return {
        "ok": True,
        "handle": handle,
        "returned_after_s": returned_after_s,
        "rejected_as_expected": rejected_as_expected,
        "rejection_error": rejection_error,
    }


async def _op_exercise(req: dict[str, object], sessions: _Sessions) -> dict[str, object]:
    handle = req["handle"]  # type: ignore[assignment]
    assert isinstance(handle, str)
    group = sessions.get(handle)
    result = await group.call_tool("search", {"query": "shutdown integrity"})
    return {"ok": True, "result": result.structured_content}


async def _op_teardown(req: dict[str, object], sessions: _Sessions) -> dict[str, object]:
    """Closes the group. Called for cleanup after the measurement window this
    scenario cares about has already closed (see module docstring); its
    timing is not part of that measurement.
    """
    handle = req["handle"]  # type: ignore[assignment]
    assert isinstance(handle, str)
    group = sessions.pop(handle)
    t0 = time.monotonic()
    await group.__aexit__(None, None, None)
    return {"ok": True, "returned_after_s": time.monotonic() - t0}


async def _dispatch(req: dict[str, object], sessions: _Sessions) -> dict[str, object]:
    op = req.get("op")
    if op == "declare_capabilities":
        return {"ok": True, "capabilities": ["stdio"]}
    if op == "start_session":
        return await _op_start_session(req, sessions)
    if op == "exercise":
        return await _op_exercise(req, sessions)
    if op == "teardown":
        return await _op_teardown(req, sessions)
    return {"ok": False, "error": f"unsupported op for this adapter: {op!r}"}


async def _serve() -> None:
    sessions = _Sessions()
    while True:
        line = await anyio.to_thread.run_sync(sys.stdin.readline)
        if not line:
            return
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        try:
            reply = await _dispatch(req, sessions)
        except (KeyError, MCPError, OSError) as exc:
            reply = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt, BrokenPipeError):
        anyio.run(_serve)


if __name__ == "__main__":
    main()
