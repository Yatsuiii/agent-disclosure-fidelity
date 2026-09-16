"""Verdict vocabulary for scenario results.

The states are deliberately more than pass/fail. An unarmed scenario and a
genuinely clean implementation look identical from outside the harness, so
INCONCLUSIVE exists to keep them apart. NOT_APPLICABLE exists so that a
framework lacking a capability cannot outscore a framework that has it and
implements it imperfectly.
"""

from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    FLAKY = "flaky"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"
    CONTRACT_UNCLEAR = "contract_unclear"


@dataclass(frozen=True)
class Residual:
    """A resource still attributable to the session after teardown returned."""

    kind: str
    identity: str
    detail: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TrialOutcome:
    """One repeat of one scenario.

    `settle_s` is None when residuals were still present at the deadline, which
    is what separates a leak from cleanup that is merely slow.
    """

    trial_index: int
    residuals: tuple[Residual, ...]
    teardown_return_s: float
    settle_s: float | None


@dataclass(frozen=True)
class ScenarioResult:
    """Aggregate across repeats, plus everything needed to reproduce it."""

    scenario_id: str
    adapter_id: str
    verdict: Verdict
    armed: bool
    trials: tuple[TrialOutcome, ...]
    sut_commit: str
    environment: dict[str, str]
    repro_command: str
