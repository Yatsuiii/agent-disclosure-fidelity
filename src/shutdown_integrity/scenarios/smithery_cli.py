"""Scenario for the smithery-cli discovery finding.

Not a rediscovery: found by pointing this instrument at a codebase where
nobody had filed this bug (see DISCOVERY.md for the classification and
prior-art search). Unlike the two SDK scenarios, contract.verified is
deliberately False: no stated teardown contract exists anywhere in this
project (no docstring, no README, no enforcing test, no internal invariant
elsewhere in the codebase this file's own behavior could be measured
against). Per this benchmark's own rule, that makes the honest verdict
CONTRACT_UNCLEAR rather than FAIL, no matter what a trial shows. The scenario
is still armed and run for record, because the structural observable
(a residual process, and close()'s wall-clock duration) is real regardless
of whether a maintainer ever wrote the guarantee down, and DESIGN.md's own
verdict vocabulary exists precisely to keep that distinction visible rather
than collapsing it into a bare pass/fail.
"""

from shutdown_integrity.adapter import TeardownMode
from shutdown_integrity.scenario import ContractCitation, ControlFixture, Scenario
from shutdown_integrity.verdict import Verdict

SUT_MAIN = "407ac3b33944a585357379bc213fdf1ee55464d7"

SCENARIO_UPLINK_STDIO_LEAKS_TREE = Scenario(
    scenario_id="smithery-cli/uplink-stdio-leaks-process-tree",
    contract=ContractCitation(
        source="src/lib/uplink.ts, createStdioLocalPeer's close() (no doc comment or README exists)",
        quote=(
            "No stated contract found. Searched: a doc comment on close() or the LocalPeer "
            "interface it implements (none); README.md for any mention of uplink process cleanup "
            "(none); the test covering this path, src/lib/__tests__/uplink.test.ts (mocks the peer "
            "entirely, asserts nothing about spawned-process behavior); an internal invariant "
            "elsewhere in this codebase to measure this file's own behavior against (the two "
            "`detached: true` usages elsewhere, homepage.ts and mcp/deploy.ts, are for the opposite "
            "purpose: deliberately daemonizing a background process with `child.unref()` so it "
            "survives the CLI exiting, not evidence of a process-group-kill invariant this file "
            "fails to follow). A changelog entry records a now-removed `cleanupChildProcess` "
            "utility that once served `dev`, `playground`, and `uplink` together, but that utility "
            "and the commands it served no longer exist in the current tree, so it is not a citable "
            "current-state fact. contract.verified is False because there is nothing to verify, not "
            "because verification was skipped."
        ),
        verified=False,
    ),
    teardown_mode=TeardownMode.GRACEFUL_CLOSE,
    required_capabilities=frozenset({"stdio"}),
    probe_kinds=("process",),
    broken_control=ControlFixture(
        name="smithery-cli-main-unpatched",
        sut_ref=SUT_MAIN,
        patch=None,
        expected=Verdict.FAIL,
    ),
    fixed_control=ControlFixture(
        # "constructed" per this run's own naming convention: no upstream PR
        # exists to source a fix from (repo is not merging contributions;
        # DISCOVERY.md records PRs #791/#793/#798/#804/#811 all open since
        # late June). Mirrors mcp/os/posix/utilities.py's
        # terminate_posix_process_tree: spawn detached, SIGTERM the process
        # group, poll, SIGKILL the group if still alive.
        name="smithery-cli-constructed-process-group-teardown",
        sut_ref=SUT_MAIN,
        patch="patches/constructed-smithery-cli-process-group-teardown.patch",
        expected=Verdict.PASS,
    ),
    known_issue_refs=(),
)

V1_SCENARIOS = (SCENARIO_UPLINK_STDIO_LEAKS_TREE,)
