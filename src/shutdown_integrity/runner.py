"""Arming gate and trial runner.

v1 scope: only the error_during_setup teardown mode is implemented, because
scenario 1 (the only scenario in scope this session, per SESSION_CONTRACT.md)
uses it exclusively. For that mode the contract boundary is not a separate
teardown call: it is the return of the connect attempt whose rejection is
being tested (see adapters/mcp_python/adapter_main.py). Other teardown modes
need a distinct measurement path and are a later session's problem.
"""

import json
import platform
import shlex
import time
import uuid
from pathlib import Path

from shutdown_integrity.adapter import AdapterError, SubprocessAdapter, TeardownMode
from shutdown_integrity.probes.process import ProcessTreeProbe
from shutdown_integrity.scenario import ControlFixture, Scenario
from shutdown_integrity.sut import REPO_ROOT, PreparedFixture, prepare
from shutdown_integrity.verdict import Residual, ScenarioResult, TrialOutcome, Verdict

DEFAULT_TRIALS = 10
DEFAULT_SETTLE_DEADLINE_S = 30.0
DEFAULT_POLL_INTERVAL_S = 0.1

_ADAPTER_SCRIPT = REPO_ROOT / "src" / "shutdown_integrity" / "adapters" / "mcp_python" / "adapter_main.py"
_LIBRARY_SERVER = REPO_ROOT / "src" / "shutdown_integrity" / "adapters" / "mcp_python" / "fixtures" / "library_server.py"
_WEB_SERVER = REPO_ROOT / "src" / "shutdown_integrity" / "adapters" / "mcp_python" / "fixtures" / "web_server.py"

_PROBES = {"process": ProcessTreeProbe()}


def _fresh_tag() -> str:
    return f"trial-{uuid.uuid4().hex}"


def _poll_until_empty(
    probe_kinds: tuple[str, ...],
    trial_tag: str,
    residual_filter,
    deadline_s: float,
    poll_interval_s: float,
) -> tuple[tuple[Residual, ...], float | None]:
    """Polls every probe in `probe_kinds` to `deadline_s`, filtering each
    snapshot through `residual_filter` (a Resource -> bool predicate that
    picks out the resources this scenario actually considers a violation,
    e.g. only the rejected-role process, not the legitimately-connected one).

    Returns the last observed residual set and the wall time at which it
    first went empty, or None if it never did before the deadline. Never
    sleep-then-assert: every iteration re-observes, so cleanup that finishes
    between polls is captured at its real time rather than rounded up to the
    next fixed sleep.
    """
    start = time.monotonic()
    last_residuals: tuple[Residual, ...] = ()
    while True:
        now = time.monotonic()
        all_residuals: list[Residual] = []
        for kind in probe_kinds:
            for resource in _PROBES[kind].snapshot(trial_tag):
                if residual_filter(resource):
                    all_residuals.append(Residual(kind=resource.kind, identity=resource.identity, detail=resource.detail))
        last_residuals = tuple(all_residuals)
        if not last_residuals:
            return last_residuals, now - start
        if now - start > deadline_s:
            return last_residuals, None
        time.sleep(poll_interval_s)


def _rejected_role_residual(resource) -> bool:
    return resource.detail.get("SHUTDOWN_INTEGRITY_ROLE") == "rejected"


def _run_rejected_connect_trial(
    scenario: Scenario,
    fixture: ControlFixture,
    settle_deadline_s: float,
    trial_index: int,
    trial_tag: str | None = None,
) -> TrialOutcome:
    """One repeat of scenario 1 against one control fixture.

    `trial_tag` lets the arming gate's negative-control trial (acceptance
    gate 3: point the probe at the wrong tag) reuse this exact trial shape
    while observing under a tag that can never match.
    """
    prepared = prepare(fixture)
    tag = trial_tag if trial_tag is not None else _fresh_tag()
    adapter = SubprocessAdapter("mcp-python", prepared.python, _ADAPTER_SCRIPT, tag)
    try:
        adapter.declare_capabilities()
        spec = {
            "accepted_server": {"command": str(prepared.python), "args": [str(_LIBRARY_SERVER)]},
            "rejected_server": {"command": str(prepared.python), "args": [str(_WEB_SERVER)]},
        }
        t0 = time.monotonic()
        reply = adapter.start_session_raw(spec)
        teardown_return_s = time.monotonic() - t0
        if not reply.get("ok"):
            raise AdapterError(f"start_session failed unexpectedly: {reply.get('error')}")
        if not reply.get("rejected_as_expected"):
            raise AdapterError(
                "the deliberate tool-name collision did not raise MCPError; the repro no longer "
                "triggers the condition this scenario measures, which is a harness fault, not a finding"
            )

        residuals, settle_s = _poll_until_empty(
            scenario.probe_kinds, tag, _rejected_role_residual, settle_deadline_s, DEFAULT_POLL_INTERVAL_S
        )
    finally:
        adapter.close()

    return TrialOutcome(
        trial_index=trial_index,
        residuals=residuals,
        teardown_return_s=teardown_return_s,
        settle_s=settle_s,
    )


def _run_trials(
    scenario: Scenario, fixture: ControlFixture, trials: int, settle_deadline_s: float
) -> tuple[TrialOutcome, ...]:
    if scenario.teardown_mode != TeardownMode.ERROR_DURING_SETUP:
        raise NotImplementedError(
            f"runner v1 only implements teardown_mode=ERROR_DURING_SETUP, scenario declares {scenario.teardown_mode}"
        )
    return tuple(_run_rejected_connect_trial(scenario, fixture, settle_deadline_s, i) for i in range(trials))


def _outcomes_agree_with(outcomes: tuple[TrialOutcome, ...], expected: Verdict) -> bool:
    if expected == Verdict.FAIL:
        return all(o.settle_s is None for o in outcomes)
    if expected == Verdict.PASS:
        return all(o.settle_s is not None for o in outcomes)
    raise ValueError(f"a control fixture's expected verdict must be PASS or FAIL, got {expected}")


def arm(scenario: Scenario, trials: int = DEFAULT_TRIALS, settle_deadline_s: float = DEFAULT_SETTLE_DEADLINE_S) -> bool:
    """Whether this scenario provably distinguishes a broken SUT from a fixed one.

    Runs both control fixtures and requires the broken one to fail and the
    fixed one to pass, unanimously. Until that holds, a harness bug and a
    real finding are indistinguishable: a probe reading the wrong namespace
    fails against everything, and a probe silently returning nothing passes
    against everything. Unarmed scenarios may only report INCONCLUSIVE.
    """
    broken_outcomes = _run_trials(scenario, scenario.broken_control, trials, settle_deadline_s)
    if not _outcomes_agree_with(broken_outcomes, scenario.broken_control.expected):
        return False
    fixed_outcomes = _run_trials(scenario, scenario.fixed_control, trials, settle_deadline_s)
    return _outcomes_agree_with(fixed_outcomes, scenario.fixed_control.expected)


def arm_negative_control(
    scenario: Scenario, trials: int = 1, settle_deadline_s: float = DEFAULT_SETTLE_DEADLINE_S
) -> bool:
    """Deliberately breaks attribution by probing under a tag no process
    carries, against the broken fixture where a real residual definitely
    exists. A probe that still reports PASS here is broken (HANDOFF.md
    acceptance gate 3: a gate that has never been shown to trip is not a
    gate). Returns True if the gate correctly refuses to call this armed.
    """
    wrong_tag = f"wrong-{uuid.uuid4().hex}"
    outcomes = tuple(
        _run_rejected_connect_trial(scenario, scenario.broken_control, settle_deadline_s, i, trial_tag=wrong_tag)
        for i in range(trials)
    )
    misreports_as_passing = _outcomes_agree_with(outcomes, Verdict.PASS)
    return not misreports_as_passing


def _aggregate(outcomes: tuple[TrialOutcome, ...]) -> Verdict:
    all_pass = all(o.settle_s is not None for o in outcomes)
    all_fail = all(o.settle_s is None for o in outcomes)
    if all_pass:
        return Verdict.PASS
    if all_fail:
        return Verdict.FAIL
    return Verdict.FLAKY


def run(
    scenario: Scenario,
    fixture: ControlFixture,
    trials: int = DEFAULT_TRIALS,
    settle_deadline_s: float = DEFAULT_SETTLE_DEADLINE_S,
) -> ScenarioResult:
    """Runs one scenario against one already-armed fixture `trials` times and
    aggregates. Never sleeps then asserts. A split result across trials is
    FLAKY, reported rather than retried: teardown that works seven times in
    ten is itself a finding.

    Callers must arm() the scenario first; run() does not check armed-ness
    itself; that check belongs to whatever assembles the final report, since
    the arming trials and the reported trials are deliberately separate runs.
    """
    outcomes = _run_trials(scenario, fixture, trials, settle_deadline_s)
    prepared = prepare(fixture)
    return ScenarioResult(
        scenario_id=scenario.scenario_id,
        adapter_id="mcp-python",
        verdict=_aggregate(outcomes),
        armed=True,
        trials=outcomes,
        sut_commit=fixture.sut_ref,
        environment={"platform": platform.platform(), "python": platform.python_version()},
        repro_command=_repro_command(prepared),
    )


def _repro_command(prepared: PreparedFixture) -> str:
    """A literal, copy-pasteable command. Backgrounds the adapter with its
    stdin held open for 5s after the request (plain `<<<` closes stdin the
    instant the request is sent, which ends the adapter's read loop and lets
    it exit before a human has time to inspect anything), then greps for the
    rejected-role residual while that window is still open. Verified by hand
    against main-unpatched: the grep hits at t+1.5s.
    """
    spec = {
        "accepted_server": {"command": str(prepared.python), "args": [str(_LIBRARY_SERVER)]},
        "rejected_server": {"command": str(prepared.python), "args": [str(_WEB_SERVER)]},
    }
    request = shlex.quote(json.dumps({"op": "start_session", "spec": spec}))
    repro_python = Path(prepared.python).relative_to(REPO_ROOT)
    repro_adapter = _ADAPTER_SCRIPT.relative_to(REPO_ROOT)
    launch = shlex.quote(f"(echo {request}; sleep 5) | {repro_python} {repro_adapter}")
    return (
        f"SHUTDOWN_INTEGRITY_TRIAL=demo bash -c {launch} & sleep 1.5; "
        f"ps -eo pid,ppid,cmd --no-headers | grep web_server.py | grep -v grep; wait"
    )
