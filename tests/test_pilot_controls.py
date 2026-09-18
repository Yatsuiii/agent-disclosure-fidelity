"""Controls-gate proof for the agent-side pilot.

Slow: each test runs a real `claude -p` session end to end. Not part of a
fast unit-test loop; this is the acceptance-gate evidence PILOT_BRIEF.md asks
for (gate 1: both controls pass before any episode is trusted). Run
explicitly: `pytest tests/test_pilot_controls.py -v`.
"""

import shutil
import tempfile
from pathlib import Path

from shutdown_integrity.pilot.episode import run_episode
from shutdown_integrity.pilot.tasks import NEGATIVE_CONTROL, POSITIVE_CONTROL


def test_positive_control_leaves_a_residual():
    """The detector must find a deliberately-left-running server. A detector
    that has never been shown to trip is not a detector.
    """
    run_root = Path(tempfile.mkdtemp(prefix="pilot-control-positive-"))
    try:
        bundle = run_episode(POSITIVE_CONTROL, run_root)
        assert not bundle.aborted, bundle.abort_reason
        assert bundle.residual_processes, "positive control left no residual process"
        for residual in bundle.residual_processes:
            assert residual["pid"]
            assert residual["cmdline"]
    finally:
        for detail in getattr(bundle, "residual_processes", ()):
            try:
                import os
                import signal

                os.kill(int(detail["pid"]), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, ValueError):
                pass
        shutil.rmtree(run_root, ignore_errors=True)


def test_negative_control_leaves_nothing():
    """A pure-computation task must return zero residual and zero filesystem
    delta. If this fails, the probe or the episode harness has a false
    positive and no episode result downstream is trustworthy.
    """
    run_root = Path(tempfile.mkdtemp(prefix="pilot-control-negative-"))
    try:
        bundle = run_episode(NEGATIVE_CONTROL, run_root)
        assert not bundle.aborted, bundle.abort_reason
        assert bundle.residual_processes == ()
        assert bundle.fs_delta.is_empty, bundle.fs_delta
    finally:
        shutil.rmtree(run_root, ignore_errors=True)
