"""Out-of-process adapter protocol.

The runner never imports the SDK under test. Each adapter is a subprocess
speaking newline-delimited JSON on stdin and stdout. This keeps the runner
language-agnostic (a Node adapter looks identical to a Python one), isolates
adapter crashes from the run, gives the probes a clean external vantage point,
and keeps the runner's own event loop and garbage collector out of the
measurement.

Wire protocol, one JSON object per line:

    -> {"op": "declare_capabilities"}
    <- {"ok": true, "capabilities": ["rebind", "streamable_http"]}

    -> {"op": "start_session", "spec": {...}}
    <- {"ok": true, "handle": "s1"}

    -> {"op": "exercise", "handle": "s1"}
    <- {"ok": true}

    -> {"op": "teardown", "handle": "s1", "mode": "graceful_close"}
    <- {"ok": true, "returned_after_s": 0.031}

Failures reply {"ok": false, "error": "..."}. An adapter that cannot honour an
op must say so rather than silently succeeding, because a silent success is
indistinguishable from a clean teardown.
"""

import contextlib
import json
import os
import signal
import subprocess
from enum import Enum
from pathlib import Path
from typing import Protocol


class TeardownMode(str, Enum):
    """How the session is ended.

    Bugs cluster in the non-happy paths. Testing only GRACEFUL_CLOSE finds
    nothing: issue 3490 is ERROR_DURING_SETUP, issue 2150 is PROCESS_SHUTDOWN.
    """

    GRACEFUL_CLOSE = "graceful_close"
    CONTEXT_EXIT = "context_exit"
    PROCESS_SHUTDOWN = "process_shutdown"
    ABRUPT_CANCEL = "abrupt_cancel"
    ERROR_DURING_SETUP = "error_during_setup"


class Adapter(Protocol):
    """Runner-side handle to one adapter subprocess."""

    adapter_id: str

    def declare_capabilities(self) -> frozenset[str]: ...

    def start_session(self, spec: dict[str, object]) -> str: ...

    def exercise(self, handle: str) -> None: ...

    def teardown(self, handle: str, mode: TeardownMode) -> float:
        """Returns seconds until the teardown call returned.

        That return is the contract boundary: the point at which the SDK has
        claimed the session is finished. Everything the probes find after it is
        a residual.
        """
        ...

    def rebind(self, handle: str) -> str: ...


class AdapterError(RuntimeError):
    """The adapter subprocess reported ok: false, or the wire protocol broke."""


class SubprocessAdapter:
    """Runner-side proxy for one adapter subprocess speaking the wire protocol.

    One instance per trial: a fresh subprocess is what keeps a hung or
    crashed adapter, or state left over from a scenario's own repro, from
    bleeding into the next trial. `close()` kills the subprocess's whole
    process group, since a killed direct child can still leave descendants
    behind (the same reparenting case ProcessTreeProbe exists to catch), so a
    plain terminate() would be an insufficient hygiene step.
    """

    def __init__(
        self,
        adapter_id: str,
        python: str | Path,
        script: str | Path,
        trial_tag: str,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.adapter_id = adapter_id
        env = os.environ.copy()
        env["SHUTDOWN_INTEGRITY_TRIAL"] = trial_tag
        if extra_env:
            env.update(extra_env)
        self._proc = subprocess.Popen(
            [str(python), str(script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            start_new_session=True,
        )

    def _call(self, req: dict[str, object]) -> dict[str, object]:
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None
        self._proc.stdin.write(json.dumps(req) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            stderr = self._proc.stderr.read() if self._proc.stderr else ""
            raise AdapterError(f"adapter subprocess closed stdout before replying to {req['op']}.\nstderr:\n{stderr}")
        return json.loads(line)

    def declare_capabilities(self) -> frozenset[str]:
        reply = self._call({"op": "declare_capabilities"})
        if not reply.get("ok"):
            raise AdapterError(f"declare_capabilities failed: {reply.get('error')}")
        return frozenset(reply["capabilities"])  # type: ignore[arg-type]

    def start_session(self, spec: dict[str, object]) -> str:
        reply = self._call({"op": "start_session", "spec": spec})
        if not reply.get("ok"):
            raise AdapterError(f"start_session failed: {reply.get('error')}")
        return reply["handle"]  # type: ignore[return-value]

    def start_session_raw(self, spec: dict[str, object]) -> dict[str, object]:
        """Like start_session, but returns the full reply rather than just the
        handle. Some scenarios (error_during_setup) measure fields the plain
        Adapter protocol has no place for, such as `returned_after_s` for the
        call whose failure IS the contract boundary being tested.
        """
        return self._call({"op": "start_session", "spec": spec})

    def exercise(self, handle: str) -> None:
        reply = self._call({"op": "exercise", "handle": handle})
        if not reply.get("ok"):
            raise AdapterError(f"exercise failed: {reply.get('error')}")

    def teardown(self, handle: str, mode: TeardownMode) -> float:
        reply = self._call({"op": "teardown", "handle": handle, "mode": mode.value})
        if not reply.get("ok"):
            raise AdapterError(f"teardown failed: {reply.get('error')}")
        return reply["returned_after_s"]  # type: ignore[return-value]

    def rebind(self, handle: str) -> str:
        reply = self._call({"op": "rebind", "handle": handle})
        if not reply.get("ok"):
            raise AdapterError(f"rebind failed: {reply.get('error')}")
        return reply["handle"]  # type: ignore[return-value]

    def close(self) -> None:
        """Hygiene kill, not a measurement. Idempotent."""
        if self._proc.poll() is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            os.killpg(self._proc.pid, signal.SIGKILL)
        self._proc.wait(timeout=5)
