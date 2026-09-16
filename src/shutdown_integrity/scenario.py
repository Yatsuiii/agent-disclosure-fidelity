"""Scenario declaration: what is tested, against what stated expectation."""

from dataclasses import dataclass

from shutdown_integrity.adapter import TeardownMode
from shutdown_integrity.verdict import Verdict


@dataclass(frozen=True)
class ContractCitation:
    """Where the violated expectation is actually written down.

    A FAIL is only defensible if the expectation comes from something the
    maintainers own: a spec line, a docstring, an invariant the surrounding
    code already maintains elsewhere. An expectation the benchmark invented is
    an opinion, and gets reported as CONTRACT_UNCLEAR instead.
    """

    source: str
    quote: str
    verified: bool


@dataclass(frozen=True)
class ControlFixture:
    """A build of the SUT whose verdict is known in advance.

    `expected` is FAIL for the broken control and PASS for the fixed one. The
    scenario is armed only when both land as expected.
    """

    name: str
    sut_ref: str
    patch: str | None
    expected: Verdict


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    contract: ContractCitation
    teardown_mode: TeardownMode
    required_capabilities: frozenset[str]
    probe_kinds: tuple[str, ...]
    broken_control: ControlFixture
    fixed_control: ControlFixture
    known_issue_refs: tuple[str, ...]
    """Empty means a FAIL here is a candidate novel finding, not a rediscovery."""
