"""Arming gate integration tests for the TypeScript SDK scenario (issue #2023).

Slow (spawns real Node subprocesses, including a wrapper + grandchild tree,
against a real SUT build), so this is not part of a fast unit-test loop; it
is the acceptance-gate evidence HANDOFF.md and the cross-language checkpoint
ask for. Run explicitly: `pytest tests/test_typescript_adapter.py -v`.

Mirrors tests/test_arming_gate.py's shape and its choice of a short settle
deadline for the same reason: this scenario's leak also has no "slow but
eventually cleans up" case. The unpatched close() call sequence (stdin.end,
wait 2s, SIGTERM the direct child, wait 2s, SIGKILL) never reaches the
grandchild at all, so a longer deadline would only make FAIL trials pay a
wait with no chance of a different outcome.
"""

from shutdown_integrity import runner
from shutdown_integrity.adapters.typescript_sdk.harness import STDIO_CLOSE_LEAKS_TREE_HARNESS
from shutdown_integrity.scenarios.typescript_sdk import SCENARIO_STDIO_CLOSE_LEAKS_TREE
from shutdown_integrity.verdict import Verdict

_SETTLE_DEADLINE_S = 5.0


def test_negative_control_trips_the_gate():
    """HANDOFF.md acceptance gate 3, proven independently for this adapter
    rather than assumed to carry over from the Python one: a probe pointed at
    the wrong trial tag, run against the broken fixture where a real residual
    exists, must not report PASS.
    """
    gate_tripped = runner.arm_negative_control(
        SCENARIO_STDIO_CLOSE_LEAKS_TREE, STDIO_CLOSE_LEAKS_TREE_HARNESS, trials=2, settle_deadline_s=_SETTLE_DEADLINE_S
    )
    assert gate_tripped


def test_scenario_arms_against_both_controls():
    """FAIL against unpatched typescript-sdk main in 10/10, PASS against
    main+pr2024 in 10/10, zero flakiness either direction.
    """
    armed = runner.arm(
        SCENARIO_STDIO_CLOSE_LEAKS_TREE, STDIO_CLOSE_LEAKS_TREE_HARNESS, trials=10, settle_deadline_s=_SETTLE_DEADLINE_S
    )
    assert armed


def test_run_against_broken_control_reports_fail_with_grandchild_evidence():
    """HANDOFF.md acceptance gate 2: the residual a FAIL trial catches is
    specifically the orphaned grandchild (the real MCP server spawned through
    wrapper.mjs), not the direct child (the wrapper itself, which close()
    does kill even on unpatched code). Also covers acceptance gate 4: PIDs,
    cmdlines, timings, and a working repro in the evidence bundle.
    """
    result = runner.run(
        SCENARIO_STDIO_CLOSE_LEAKS_TREE,
        SCENARIO_STDIO_CLOSE_LEAKS_TREE.broken_control,
        STDIO_CLOSE_LEAKS_TREE_HARNESS,
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
            assert "fixtures/server.mjs" in residual.detail["cmdline"], (
                "residual must be the real MCP server (the grandchild), not the wrapper "
                f"(the direct child, which close() does kill): {residual.detail['cmdline']}"
            )
        assert trial.teardown_return_s > 0
    assert result.sut_commit
    assert result.repro_command


def test_run_against_fixed_control_reports_pass():
    result = runner.run(
        SCENARIO_STDIO_CLOSE_LEAKS_TREE,
        SCENARIO_STDIO_CLOSE_LEAKS_TREE.fixed_control,
        STDIO_CLOSE_LEAKS_TREE_HARNESS,
        trials=3,
        settle_deadline_s=_SETTLE_DEADLINE_S,
    )
    assert result.verdict == Verdict.PASS
    for trial in result.trials:
        assert trial.settle_s is not None
        assert trial.residuals == ()
