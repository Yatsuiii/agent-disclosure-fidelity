"""Scenarios for the MCP Python SDK.

Both declared scenarios now have citations verified against source (SDK code
plus the linked GitHub issue/PR, read directly, not inferred from a prior
declaration). Verification is necessary but not sufficient to run a scenario
for record, though: SCENARIO_REJECTED_CONNECT is armed and has run (see
SESSION_CONTRACT.md history). SCENARIO_SHUTDOWN_DRAIN is not, because the
resource it tests leaks in-process rather than as an OS process, and no probe
for that exists yet (see its probe_kinds comment). Do not run it for record
until a probe that can actually see the leak is built and armed.
"""

from shutdown_integrity.adapter import TeardownMode
from shutdown_integrity.scenario import ContractCitation, ControlFixture, Scenario
from shutdown_integrity.verdict import Verdict

SUT_MAIN = "9972c21aa42054fb1450c5fc614761ed11847ec6"

SCENARIO_REJECTED_CONNECT = Scenario(
    scenario_id="mcp-py/rejected-connect-leaks-transport",
    contract=ContractCitation(
        source="src/mcp/client/session_group.py, _establish_session except branch",
        quote=(
            "_establish_session already closes the session's exit stack when setup fails "
            "(`except Exception: await session_stack.aclose(); raise`). connect_to_server "
            "does not maintain that same invariant when _aggregate_components rejects the "
            "session after establishment, so the transport stays registered and running."
        ),
        verified=True,
    ),
    teardown_mode=TeardownMode.ERROR_DURING_SETUP,
    required_capabilities=frozenset({"stdio"}),
    # fd is out of scope this session (SESSION_CONTRACT.md): FdSocketProbe is
    # still a stub. Narrowed here rather than left declared-but-unchecked,
    # since a probe that silently returns nothing is exactly the false-PASS
    # failure mode this benchmark exists to avoid (DESIGN.md, arming gate).
    probe_kinds=("process",),
    broken_control=ControlFixture(
        name="main-unpatched",
        sut_ref=SUT_MAIN,
        patch=None,
        expected=Verdict.FAIL,
    ),
    fixed_control=ControlFixture(
        name="main-plus-pr3502",
        sut_ref=SUT_MAIN,
        patch="patches/pr3502-close-rejected-transport.patch",
        expected=Verdict.PASS,
    ),
    known_issue_refs=("modelcontextprotocol/python-sdk#3490",),
)

SCENARIO_SHUTDOWN_DRAIN = Scenario(
    scenario_id="mcp-py/shutdown-does-not-drain-sessions",
    contract=ContractCitation(
        source=(
            "src/mcp/server/streamable_http_manager.py, StreamableHTTPSessionManager.run(), "
            "the finally block on manager shutdown"
        ),
        quote=(
            "On shutdown the finally block does `tg.cancel_scope.cancel()` then "
            "`self._server_instances.clear()`, with no call to `transport.terminate()` on any "
            "tracked transport first. Contrast `_handle_stateless_request`'s own finally block "
            "in the same file, which does call `await http_transport.terminate()` before "
            "returning: the SDK's own code already treats terminate-before-drop as the correct "
            "shutdown invariant for a transport it owns, just not on this path. terminate() "
            "itself (src/mcp/server/streamable_http.py) only closed `_request_streams`, not "
            "`_sse_stream_writers`, so even a call to terminate() would not have fully closed "
            "an active SSE response prior to PR #3218's fix. Verified by reading both files "
            "directly against the pinned commit, not by trusting the issue report alone; the "
            "issue's own root-cause analysis (by a non-maintainer commenter) independently "
            "names the same two gaps."
        ),
        verified=True,
    ),
    teardown_mode=TeardownMode.PROCESS_SHUTDOWN,
    required_capabilities=frozenset({"streamable_http"}),
    # Unlike SCENARIO_REJECTED_CONNECT, the leaked resource here is not an OS
    # process: streamable-http sessions run in-process as ASGI tasks and SSE
    # stream writers. ProcessTreeProbe cannot see this at all, and FdSocketProbe
    # is still an unimplemented stub. This scenario cannot be armed with the
    # probe layer that exists today; DESIGN.md's "known weak point" already
    # flags in-process resource leaks as v1's uncovered category. probe_kinds
    # left as the (unimplemented) fd probe rather than silently substituting
    # process, which would just always report PASS (nothing to find) and read
    # as a false clean bill of health.
    probe_kinds=("fd",),
    broken_control=ControlFixture(
        name="main-unpatched",
        sut_ref=SUT_MAIN,
        patch=None,
        expected=Verdict.FAIL,
    ),
    fixed_control=ControlFixture(
        name="main-plus-pr3218",
        sut_ref=SUT_MAIN,
        patch="patches/pr3218-terminate-streamable-http-sessions-on-shutdown.patch",
        expected=Verdict.PASS,
    ),
    # The scenario's own quote is issue #2150's title verbatim (gh issue view,
    # verified this session). The declaration previously cited #2958 here,
    # which is a different, unrelated bug (CLOSE_WAIT accumulation from
    # missing disconnect cleanup during normal operation, not shutdown), and
    # pointed fixed_control at PR #2982, whose own description says
    # "Fixes #2958" and which does not exist as a vendored patch on disk.
    # PR #3218 (closed unmerged, same auto-close pattern as PR #3502; verified
    # via `gh pr view`/`gh pr diff` and `git apply --check` against the pinned
    # commit) fixes #2150 specifically, with regression tests, superseding an
    # earlier unmerged attempt (#3125) it explicitly says it continues.
    known_issue_refs=("modelcontextprotocol/python-sdk#2150",),
)

V1_SCENARIOS = (SCENARIO_REJECTED_CONNECT, SCENARIO_SHUTDOWN_DRAIN)
