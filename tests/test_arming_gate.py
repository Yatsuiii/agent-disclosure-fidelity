"""Arming gate integration tests for scenario 1.

Slow (spawns real stdio subprocesses against a real SUT build), so this is not
part of a fast unit-test loop; it is the acceptance-gate evidence HANDOFF.md
asks for. Run explicitly: `pytest tests/test_arming_gate.py -v`.
"""

from shutdown_integrity import runner
from shutdown_integrity.scenarios.mcp_python import SCENARIO_REJECTED_CONNECT
from shutdown_integrity.verdict import Verdict

# This scenario's leak has no "slow but eventually cleans up" case: the
# patched path closes the rejected session synchronously inside the same
# connect_to_server call, and the unpatched path never closes it on its own
# at all (only an explicit later teardown of the whole group would, which
# these trials deliberately never call; see runner.py module docstring). A
# long deadline would only make FAIL trials pay the full wait for no benefit.
_SETTLE_DEADLINE_S = 3.0


def test_negative_control_trips_the_gate():
    """HANDOFF.md acceptance gate 3: deliberately break the probe (point it at
    the wrong tag) and confirm the arming gate refuses to report a verdict. A
    gate that has never been shown to trip is not a gate. Run against the
    broken fixture, where a real residual exists, so a false PASS here can
    only come from broken attribution, never from a coincidentally clean SDK.
    """
    gate_tripped = runner.arm_negative_control(SCENARIO_REJECTED_CONNECT, trials=2, settle_deadline_s=_SETTLE_DEADLINE_S)
    assert gate_tripped


def test_scenario_arms_against_both_controls():
    """HANDOFF.md acceptance gate 1: FAIL against unpatched main in 10/10,
    PASS against main+pr3502 in 10/10, zero flakiness either direction.
    """
    armed = runner.arm(SCENARIO_REJECTED_CONNECT, trials=10, settle_deadline_s=_SETTLE_DEADLINE_S)
    assert armed


def test_run_against_broken_control_reports_fail_with_evidence():
    """HANDOFF.md acceptance gate 4: the evidence bundle for one FAIL contains
    residual PIDs with cmdlines, timings, and a working one-line repro.
    """
    result = runner.run(
        SCENARIO_REJECTED_CONNECT, SCENARIO_REJECTED_CONNECT.broken_control, trials=3, settle_deadline_s=_SETTLE_DEADLINE_S
    )
    assert result.verdict == Verdict.FAIL
    assert result.trials
    for trial in result.trials:
        assert trial.settle_s is None
        assert trial.residuals
        for residual in trial.residuals:
            assert residual.detail["pid"]
            assert residual.detail["cmdline"]
        assert trial.teardown_return_s > 0
    assert result.sut_commit
    assert result.repro_command


def test_run_against_fixed_control_reports_pass():
    result = runner.run(
        SCENARIO_REJECTED_CONNECT, SCENARIO_REJECTED_CONNECT.fixed_control, trials=3, settle_deadline_s=_SETTLE_DEADLINE_S
    )
    assert result.verdict == Verdict.PASS
    for trial in result.trials:
        assert trial.settle_s is not None
        assert trial.residuals == ()
