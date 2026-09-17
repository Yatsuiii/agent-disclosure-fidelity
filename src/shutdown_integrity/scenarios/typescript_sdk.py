"""Scenarios for the MCP TypeScript SDK.

The first scenario in a second language and a second ecosystem: it exercises
the same claim as scenarios/mcp_python.py's SCENARIO_REJECTED_CONNECT (an SDK
fails to honour its own teardown contract) through a completely different
JSON control-protocol adapter, proving the instrument generalizes rather than
being MCP-python-shaped in disguise. It is also the first scenario to close
HANDOFF.md's acceptance gate 2 (grandchild detection) against real SDK code
rather than only the synthetic sh -c fixture in tests/test_process_probe.py.
"""

from shutdown_integrity.adapter import TeardownMode
from shutdown_integrity.scenario import ContractCitation, ControlFixture, Scenario
from shutdown_integrity.verdict import Verdict

SUT_MAIN = "b65426158ed9f29aea8ef3dc09ca22d7d9d6f970"

SCENARIO_STDIO_CLOSE_LEAKS_TREE = Scenario(
    scenario_id="ts/stdio-close-leaks-process-tree",
    contract=ContractCitation(
        source=(
            "packages/client/src/client/stdio.ts, StdioClientTransport.close(); "
            "docs/get-started/first-client.md, \"Close the connection\""
        ),
        quote=(
            "close() calls `processToClose.kill(signal)` (SIGTERM then SIGKILL), which is "
            "Node's ChildProcess.kill() and signals only the direct child PID, never a process "
            "group. When the server is spawned through a wrapper (npx, uvx, python -m: the "
            "documented client example itself uses `command: 'npx', args: ['tsx', ...]`), the "
            "wrapper is the direct child and the real server is a grandchild that receives "
            "nothing. The SDK's own docs state the guarantee this violates: \"close() ends the "
            "spawned server's stdin and kills the process if it does not exit on its own\" "
            "(first-client.md). Verified by reading stdio.ts directly against the pinned commit, "
            "not by trusting the issue report alone; the issue's own reproduction steps "
            "independently describe the same wrapper shape."
        ),
        verified=True,
    ),
    teardown_mode=TeardownMode.GRACEFUL_CLOSE,
    required_capabilities=frozenset({"stdio"}),
    probe_kinds=("process",),
    broken_control=ControlFixture(
        name="ts-main-unpatched",
        sut_ref=SUT_MAIN,
        patch=None,
        expected=Verdict.FAIL,
    ),
    fixed_control=ControlFixture(
        name="ts-main-plus-pr2024",
        sut_ref=SUT_MAIN,
        patch="patches/pr2024-kill-process-tree-on-close.patch",
        expected=Verdict.PASS,
    ),
    # PR #2024 fixes #2023 unconditionally (process-group kill on close()).
    # A second candidate, PR #2596, makes the same fix opt-in via a new
    # killProcessTree option (default false); #2024 is preferred because it
    # needs no adapter-side config to activate, matching how PR #3502 and
    # PR #3218 were used as unconditional fixes in the Python scenarios.
    # Both read directly via `gh pr view`/`gh pr diff`, not inferred.
    known_issue_refs=("modelcontextprotocol/typescript-sdk#2023",),
)

V1_SCENARIOS = (SCENARIO_STDIO_CLOSE_LEAKS_TREE,)
