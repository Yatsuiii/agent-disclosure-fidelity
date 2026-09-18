"""Arming gate integration tests for the smithery-cli discovery finding.

Slow (spawns a mock WebSocket relay, drives the real shipped `serveUplink()`
through spawn/initialize/close, including a wrapper+grandchild tree), so
this is not part of a fast unit-test loop. Run explicitly:
`pytest tests/test_discovery_smithery_cli.py -v`.

Important: a PASS/FAIL verdict from this scenario is a structural
observation only (residual process exists or does not, after close()
returns). It is not a contract violation the way the two SDK scenarios are,
because contract.verified is False here (see scenarios/smithery_cli.py):
no stated teardown contract exists anywhere in this project. Per this
benchmark's own rule, the citable verdict for this finding is
CONTRACT_UNCLEAR, not FAIL, regardless of what these trials show. They are
still run for record because the structural observable is real and
prior-art-clear (see DISCOVERY.md), and DESIGN.md's own verdict vocabulary
exists to keep "we found a residual" and "a maintainer's stated guarantee is
broken" distinct rather than collapsing them.
"""

from shutdown_integrity import runner
from shutdown_integrity.adapters.smithery_cli.harness import UPLINK_STDIO_LEAKS_TREE_HARNESS
from shutdown_integrity.scenarios.smithery_cli import SCENARIO_UPLINK_STDIO_LEAKS_TREE
from shutdown_integrity.verdict import Verdict

# Mirrors test_arming_gate.py's and test_typescript_adapter.py's reasoning:
# this mechanism has no "slow but eventually cleans up" case either. The
# constructed-fixed path's process-group signal reaches every descendant
# within the same close() call that fails to reach anything on unpatched
# code, so a longer deadline would only make FAIL trials pay a longer wait
# for no different outcome.
_SETTLE_DEADLINE_S = 3.0


def test_negative_control_trips_the_gate():
    gate_tripped = runner.arm_negative_control(
        SCENARIO_UPLINK_STDIO_LEAKS_TREE,
        UPLINK_STDIO_LEAKS_TREE_HARNESS,
        trials=2,
        settle_deadline_s=_SETTLE_DEADLINE_S,
    )
    assert gate_tripped


def test_scenario_arms_against_both_controls():
    """FAIL (structural) against unpatched smithery-cli main in 10/10, PASS
    against the constructed process-group-teardown patch in 10/10, zero
    flakiness either direction.
    """
    armed = runner.arm(
        SCENARIO_UPLINK_STDIO_LEAKS_TREE,
        UPLINK_STDIO_LEAKS_TREE_HARNESS,
        trials=10,
        settle_deadline_s=_SETTLE_DEADLINE_S,
    )
    assert armed


def test_run_against_broken_control_reports_fail_with_grandchild_evidence():
    """Residual is the real MCP server (the grandchild spawned through
    wrapper.mjs), not the adapter's own tsx/esbuild-service processes, which
    also carry the trial tag but are excluded by
    SHUTDOWN_INTEGRITY_ROLE=server filtering. Also measures the second
    observable the arming task asked for: close() itself burns its full
    ~10s timeout budget rather than the ~5s the fixed control needs, because
    the still-alive grandchild holds the direct child's inherited stdout
    pipe open, so Node's 'close' event on the direct child never fires.
    """
    result = runner.run(
        SCENARIO_UPLINK_STDIO_LEAKS_TREE,
        SCENARIO_UPLINK_STDIO_LEAKS_TREE.broken_control,
        UPLINK_STDIO_LEAKS_TREE_HARNESS,
        trials=3,
        settle_deadline_s=_SETTLE_DEADLINE_S,
    )
    assert result.verdict == Verdict.FAIL
    assert result.trials
    for trial in result.trials:
        assert trial.settle_s is None
        assert trial.residuals
        for residual in trial.residuals:
            assert residual.detail["pid"]
            assert "fixtures/server.mjs" in residual.detail["cmdline"]
        # The slow-close observable: ~10s (both STDIO_KILL_TIMEOUT_MS
        # windows elapse), well above the ~5s the fixed control needs.
        assert trial.teardown_return_s > 8.0
    assert result.sut_commit
    assert result.repro_command


def test_run_against_fixed_control_reports_pass():
    result = runner.run(
        SCENARIO_UPLINK_STDIO_LEAKS_TREE,
        SCENARIO_UPLINK_STDIO_LEAKS_TREE.fixed_control,
        UPLINK_STDIO_LEAKS_TREE_HARNESS,
        trials=3,
        settle_deadline_s=_SETTLE_DEADLINE_S,
    )
    assert result.verdict == Verdict.PASS
    for trial in result.trials:
        assert trial.settle_s is not None
        assert trial.residuals == ()
        # The group signal reaches everyone within the first STDIO_KILL_TIMEOUT_MS
        # window, well under the broken control's ~10s.
        assert trial.teardown_return_s < 8.0
