# Session Contract

Objective: Verify SCENARIO_SHUTDOWN_DRAIN's contract citation against primary
source before any attempt to run it for record, correcting the declaration if
verification finds it wrong (HANDOFF.md: "Do not report a result whose ...
contract citation is still marked verified=False"; DESIGN.md: "a FAIL is only
defensible if the expectation comes from something the maintainers own").
Scope stops at a corrected, source-verified declaration plus an honest
assessment of what it takes to arm it. Do not build a new probe modality in
this session without a checkpoint; if verification shows the existing
process-only probe layer cannot measure this scenario, say so and stop rather
than force a fit.

Branch: master

Parent: HEAD

Allowed files:
- .claude/SESSION_CONTRACT.md
- src/shutdown_integrity/scenarios/mcp_python.py (correct SCENARIO_SHUTDOWN_DRAIN's
  citation, known_issue_refs, and fixed_control only; SCENARIO_REJECTED_CONNECT
  stays as-is, already verified and armed in a prior session)
- patches/** (vendor the correct fixed-control patch, sourced from an actual
  GitHub PR against the pinned SUT commit; remove the reference to the
  nonexistent pr2982 patch file)

Non-goals:
- No FdSocketProbe or behavioral-probe implementation this session. That is
  new probe-layer work (DESIGN.md's "known weak point" and "open design
  question 1"), not a citation fix, and needs its own checkpoint.
- No arming run, no `runner.run()` against this scenario. Arming requires a
  working probe for the resource actually being leaked; until that exists,
  any "verdict" would be exactly the kind of false reading HANDOFF.md warns
  four prior false readings all came from.
- No edits to suts/mcp-python-sdk itself.
- No GitHub writes: read-only `gh issue view` / `gh pr view` / `gh pr diff`
  only, to verify citations and source a patch. No comments, no issues, no PRs.
- No changes to SCENARIO_REJECTED_CONNECT or its supporting adapter/runner/probe
  code built in the prior session.

Baseline: SCENARIO_SHUTDOWN_DRAIN currently declares contract.verified=False,
a quote matching issue #2150's title, known_issue_refs citing #2958 (a
different, unrelated bug: CLOSE_WAIT accumulation from missing disconnect
cleanup, not shutdown termination), and a fixed_control patch file
(pr2982-streamable-http-disconnect-cleanup.patch) that does not exist on disk
and, per PR #2982's own description ("Fixes #2958"), fixes the wrong issue
even if it did exist.

Acceptance gates:
1. contract.source cites the actual SDK code path (file + function), not just
   an issue number, matching DESIGN.md's citation standard.
2. contract.verified=True only if the quoted expectation and the cited code
   were both read directly this session (source file, `gh issue view`, `gh pr
   diff`), not inferred from the scenario's own prior (wrong) declaration.
3. known_issue_refs correctly names the issue whose title matches the quoted
   text, confirmed via `gh issue view`.
4. fixed_control references a patch that (a) is vendored into patches/, (b)
   `git apply --check`s cleanly against the pinned SUT commit, and (c) fixes
   the cited issue specifically (confirmed by reading the PR body/diff, not
   by its filename).
5. Final report states plainly whether the scenario can be armed with the
   process-only probe layer that exists today, and if not, what probe
   modality it actually needs.

Verification:
- `gh issue view <n> --repo modelcontextprotocol/python-sdk` for both the
  cited and previously-miscited issue numbers.
- `git apply --check` of the vendored patch against suts/mcp-python-sdk.
- `ruff check src/`.
- `git status` shows only files in the allowed scope.

Status: active
