"""ProcessTreeProbe unit tests.

Two things must be proven before this probe is trusted anywhere else in the
benchmark, per HANDOFF.md's acceptance gates: it finds a residual that is a
grandchild, not only a direct child, and it can be shown to fail closed (miss
everything) when pointed at the wrong tag, which is exactly the failure mode
the arming gate exists to catch.
"""

import os
import signal
import subprocess
import sys
import time
import uuid

from shutdown_integrity.probes.process import ProcessTreeProbe

_POLL_DEADLINE_S = 5.0
_POLL_INTERVAL_S = 0.05


def _fresh_tag() -> str:
    return f"test-{uuid.uuid4().hex}"


def _poll_until(predicate, deadline_s: float = _POLL_DEADLINE_S):
    """Polls `predicate()` to a deadline. Never sleep-then-assert (HANDOFF.md)."""
    start = time.monotonic()
    while True:
        result = predicate()
        if result:
            return result
        if time.monotonic() - start > deadline_s:
            return result
        time.sleep(_POLL_INTERVAL_S)


def _spawn_tagged(args: list[str], tag: str) -> subprocess.Popen[bytes]:
    env = {"SHUTDOWN_INTEGRITY_TRIAL": tag, "PATH": os.environ.get("PATH", "")}
    return subprocess.Popen(args, env=env, start_new_session=True)


def test_finds_direct_child():
    tag = _fresh_tag()
    proc = _spawn_tagged([sys.executable, "-c", "import time; time.sleep(30)"], tag)
    try:
        found = _poll_until(lambda: ProcessTreeProbe().snapshot(tag))
        assert len(found) == 1
        assert found[0].detail["pid"] == str(proc.pid)
        assert "time.sleep" in found[0].detail["cmdline"]
    finally:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)


def test_finds_grandchild_spawned_through_sh_wrapper():
    """sh -c '<cmd> & wait' forks a real grandchild instead of exec-replacing
    itself, which is the shape that reparents to PID 1 if only the direct
    child (sh) is killed. Ancestry-only attribution would miss it once
    orphaned; the env tag must not.
    """
    tag = _fresh_tag()
    inner = f"{sys.executable} -c 'import time; time.sleep(30)'"
    proc = _spawn_tagged(["sh", "-c", f"{inner} & wait $!"], tag)
    try:
        found = _poll_until(lambda: ProcessTreeProbe().snapshot(tag) if len(ProcessTreeProbe().snapshot(tag)) >= 2 else None)
        assert found is not None, "expected sh and its python grandchild both tagged"
        assert len(found) == 2
        pids = {r.detail["pid"] for r in found}
        assert str(proc.pid) in pids, "direct child (sh) must be found"
        grandchild_pids = pids - {str(proc.pid)}
        assert len(grandchild_pids) == 1
        (grandchild_pid,) = grandchild_pids
        grandchild = next(r for r in found if r.detail["pid"] == grandchild_pid)
        assert grandchild.detail["ppid"] != str(os.getpid()), "must not be a direct child of the test process"
        assert "time.sleep" in grandchild.detail["cmdline"]
    finally:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)


def test_wrong_tag_finds_nothing():
    """A probe pointed at a tag no process carries must report zero residuals,
    not raise and not silently return something else's processes. This is the
    failure mode the arming gate's "point it at the wrong tag" trial (HANDOFF
    acceptance gate 3) depends on being able to trigger deterministically.
    """
    tag = _fresh_tag()
    proc = _spawn_tagged([sys.executable, "-c", "import time; time.sleep(30)"], tag)
    try:
        _poll_until(lambda: ProcessTreeProbe().snapshot(tag))
        wrong_tag_result = ProcessTreeProbe().snapshot(_fresh_tag())
        assert wrong_tag_result == ()
    finally:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)


def test_dead_process_is_not_reported():
    tag = _fresh_tag()
    proc = _spawn_tagged([sys.executable, "-c", "pass"], tag)
    proc.wait(timeout=5)
    _poll_until(lambda: ProcessTreeProbe().snapshot(tag) == () or None, deadline_s=2.0)
    assert ProcessTreeProbe().snapshot(tag) == ()
