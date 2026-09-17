"""Arming gate and trial runner.

Framework-free by design (DESIGN.md's execution layer): everything here
operates on a `Scenario` plus a small `AdapterHarness`, never on a specific
SDK's paths or spec shape. Each adapter family supplies its own harness
(e.g. adapters/mcp_python/harness.py) satisfying the Protocol below; adding a
framework means writing an adapter subprocess, its fixtures, and one harness
object, not touching this file.

Two teardown-mode shapes are implemented:

- ERROR_DURING_SETUP: the contract boundary is not a separate teardown call,
  it is the return of the start_session call whose rejection is being tested
  (see adapters/mcp_python/adapter_main.py). The adapter must reply with
  `rejected_as_expected: true` when the deliberate trigger condition fires;
  `false` or a missing key means the repro did not trigger and the trial is a
  harness fault, not a finding.
- Anything else (GRACEFUL_CLOSE, CONTEXT_EXIT, PROCESS_SHUTDOWN, ...): the
  ordinary start_session / exercise / teardown(mode) sequence from adapter.py,
  where teardown()'s return is the boundary.

ABRUPT_CANCEL has no implementation yet; it needs a way to interrupt a
session mid-call, which no adapter has exercised, so it stays unhandled
rather than silently mapped onto one of the two shapes above.
"""

import platform
import time
import uuid
from typing import Protocol

from shutdown_integrity.adapter import AdapterError, SubprocessAdapter, TeardownMode
from shutdown_integrity.probes.process import ProcessTreeProbe
from shutdown_integrity.probes.base import Resource
from shutdown_integrity.scenario import ControlFixture, Scenario
from shutdown_integrity.verdict import Residual, ScenarioResult, TrialOutcome, Verdict

DEFAULT_TRIALS = 10
DEFAULT_SETTLE_DEADLINE_S = 30.0
DEFAULT_POLL_INTERVAL_S = 0.1

_PROBES = {"process": ProcessTreeProbe()}


class AdapterHarness(Protocol):
    """What the runner needs from one adapter family to drive a scenario.

    `prepare` and `launch` are split because preparing a fixture (build a
    venv, install+build a worktree) is idempotent and safe to call every
    trial, while launching starts a fresh subprocess per trial on purpose: a
    stuck or crashed adapter, or state left over from a scenario's own repro,
    must never bleed into the next trial.
    """

    adapter_id: str

    def prepare(self, fixture: ControlFixture) -> object: ...

    def launch(self, prepared: object, trial_tag: str) -> SubprocessAdapter: ...

    def build_spec(self, prepared: object) -> dict[str, object]: ...

    def residual_filter(self, resource: Resource) -> bool:
        """Which of this trial's tagged resources count as a violation.

        Not every tagged process is one: scenario 1 tags both the
        legitimately-connected server and the rejected one, and only the
        latter is evidence of the bug.
        """
        ...

    def repro_command(self, prepared: object) -> str:
        """A literal, copy-pasteable shell command reproducing one FAIL trial."""
        ...


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
    picks out the resources this scenario actually considers a violation).

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


def _run_error_during_setup_trial(adapter: SubprocessAdapter, spec: dict[str, object]) -> float:
    t0 = time.monotonic()
    reply = adapter.start_session_raw(spec)
    teardown_return_s = time.monotonic() - t0
    if not reply.get("ok"):
        raise AdapterError(f"start_session failed unexpectedly: {reply.get('error')}")
    if not reply.get("rejected_as_expected"):
        raise AdapterError(
            "the deliberate trigger condition did not fire; the repro no longer triggers the "
            "condition this scenario measures, which is a harness fault, not a finding"
        )
    return teardown_return_s


def _run_graceful_trial(adapter: SubprocessAdapter, spec: dict[str, object], mode: TeardownMode) -> float:
    handle = adapter.start_session(spec)
    adapter.exercise(handle)
    return adapter.teardown(handle, mode)


def _run_trial(
    scenario: Scenario,
    fixture: ControlFixture,
    harness: AdapterHarness,
    settle_deadline_s: float,
    trial_index: int,
    trial_tag: str | None = None,
) -> TrialOutcome:
    """One repeat of `scenario` against one control fixture.

    `trial_tag` lets the arming gate's negative-control trial (acceptance
    gate 3: point the probe at the wrong tag) reuse this exact trial shape
    while observing under a tag that can never match.
    """
    prepared = harness.prepare(fixture)
    tag = trial_tag if trial_tag is not None else _fresh_tag()
    adapter = harness.launch(prepared, tag)
    try:
        adapter.declare_capabilities()
        spec = harness.build_spec(prepared)
        if scenario.teardown_mode == TeardownMode.ERROR_DURING_SETUP:
            teardown_return_s = _run_error_during_setup_trial(adapter, spec)
        else:
            teardown_return_s = _run_graceful_trial(adapter, spec, scenario.teardown_mode)

        residuals, settle_s = _poll_until_empty(
            scenario.probe_kinds, tag, harness.residual_filter, settle_deadline_s, DEFAULT_POLL_INTERVAL_S
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
    scenario: Scenario, fixture: ControlFixture, harness: AdapterHarness, trials: int, settle_deadline_s: float
) -> tuple[TrialOutcome, ...]:
    if scenario.teardown_mode == TeardownMode.ABRUPT_CANCEL:
        raise NotImplementedError("ABRUPT_CANCEL has no trial implementation yet; see module docstring")
    return tuple(_run_trial(scenario, fixture, harness, settle_deadline_s, i) for i in range(trials))


def _outcomes_agree_with(outcomes: tuple[TrialOutcome, ...], expected: Verdict) -> bool:
    if expected == Verdict.FAIL:
        return all(o.settle_s is None for o in outcomes)
    if expected == Verdict.PASS:
        return all(o.settle_s is not None for o in outcomes)
    raise ValueError(f"a control fixture's expected verdict must be PASS or FAIL, got {expected}")


def arm(
    scenario: Scenario,
    harness: AdapterHarness,
    trials: int = DEFAULT_TRIALS,
    settle_deadline_s: float = DEFAULT_SETTLE_DEADLINE_S,
) -> bool:
    """Whether this scenario provably distinguishes a broken SUT from a fixed one.

    Runs both control fixtures and requires the broken one to fail and the
    fixed one to pass, unanimously. Until that holds, a harness bug and a
    real finding are indistinguishable: a probe reading the wrong namespace
    fails against everything, and a probe silently returning nothing passes
    against everything. Unarmed scenarios may only report INCONCLUSIVE.
    """
    broken_outcomes = _run_trials(scenario, scenario.broken_control, harness, trials, settle_deadline_s)
    if not _outcomes_agree_with(broken_outcomes, scenario.broken_control.expected):
        return False
    fixed_outcomes = _run_trials(scenario, scenario.fixed_control, harness, trials, settle_deadline_s)
    return _outcomes_agree_with(fixed_outcomes, scenario.fixed_control.expected)


def arm_negative_control(
    scenario: Scenario,
    harness: AdapterHarness,
    trials: int = 1,
    settle_deadline_s: float = DEFAULT_SETTLE_DEADLINE_S,
) -> bool:
    """Deliberately breaks attribution by probing under a tag no process
    carries, against the broken fixture where a real residual definitely
    exists. A probe that still reports PASS here is broken (HANDOFF.md
    acceptance gate 3: a gate that has never been shown to trip is not a
    gate). Returns True if the gate correctly refuses to call this armed.
    """
    wrong_tag = f"wrong-{uuid.uuid4().hex}"
    outcomes = tuple(
        _run_trial(scenario, scenario.broken_control, harness, settle_deadline_s, i, trial_tag=wrong_tag)
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
    harness: AdapterHarness,
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
    outcomes = _run_trials(scenario, fixture, harness, trials, settle_deadline_s)
    prepared = harness.prepare(fixture)
    return ScenarioResult(
        scenario_id=scenario.scenario_id,
        adapter_id=harness.adapter_id,
        verdict=_aggregate(outcomes),
        armed=True,
        trials=outcomes,
        sut_commit=fixture.sut_ref,
        environment={"platform": platform.platform(), "python": platform.python_version()},
        repro_command=harness.repro_command(prepared),
    )
