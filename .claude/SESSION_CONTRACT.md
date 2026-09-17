# Session Contract

Objective: Build the TypeScript SDK adapter and arm a scenario for
typescript-sdk#2023 (`StdioClientTransport.close()` does not kill the process
tree, leaving orphan processes) end to end, reusing the existing runner,
ProcessTreeProbe, and JSON control protocol unchanged. Per the prior
checkpoint's decision record: this is the highest-leverage next step because
it tests both of v1's real claims at once (the failure class is systemic
across SDKs, one instrument measures it uniformly) with zero new probe work,
and it closes HANDOFF.md's still-open acceptance gate 2 (grandchild detection)
on real code instead of only a synthetic `sh -c` fixture. Citation for #2023
is verified this session before any build (see Baseline); its fixed control
(PR #2024) is sourced the same way PR #3502 and PR #3218 were: read directly,
applies cleanly to the pinned commit, closed-unmerged rather than rejected on
merit.

Branch: master

Parent: HEAD

Allowed files:
- .claude/SESSION_CONTRACT.md
- src/shutdown_integrity/scenarios/typescript_sdk.py (new: the #2023 scenario
  declaration, mirroring scenarios/mcp_python.py's shape)
- src/shutdown_integrity/adapters/typescript_sdk/** (new: the Node adapter
  subprocess speaking the same NDJSON wire protocol as adapter_main.py, and
  its two fixture stdio servers)
- src/shutdown_integrity/runner.py: generalizing to an adapter-agnostic
  `AdapterHarness` Protocol turned out to be necessary, not optional. The
  existing runner hardcoded MCP-python paths (`_ADAPTER_SCRIPT`,
  `_LIBRARY_SERVER`, `_WEB_SERVER`) directly into its trial functions; a
  second adapter family cannot be added without either duplicating the whole
  trial/arm/run machinery or extracting that per-adapter glue behind a small
  shared interface. Chose the latter (DESIGN.md's own stated goal: "adding a
  framework is a day of work"). Scenario 1's behavior, gates, and evidence
  output must be bit-for-bit unaffected by this refactor.
- src/shutdown_integrity/adapter.py: `SubprocessAdapter` needs an optional
  `extra_env` constructor param so the TypeScript harness can pass
  `SHUTDOWN_INTEGRITY_SUT_ROOT` without changing the wire protocol or any
  existing call site's behavior.
- src/shutdown_integrity/adapters/mcp_python/harness.py (new): extracts the
  existing inline MCP-python glue (adapter script path, fixture server paths,
  spec-building, residual filter, repro command) out of runner.py into the
  Protocol shape the generalized runner now consumes. Scenario 1's own files
  (adapter_main.py, fixtures/, scenarios/mcp_python.py) stay untouched.
- src/shutdown_integrity/sut.py: adds `prepare_node()` and a generic worktree
  helper shared with the existing Python `prepare()`, which now delegates to
  it instead of duplicating the git-worktree logic. `prepare()`'s own
  behavior and return type for existing callers are unchanged.
- patches/pr2024-kill-process-tree-on-close.patch
- tests/test_typescript_adapter.py (new, mirroring test_arming_gate.py)
- tests/test_arming_gate.py: call sites only, updated for the new `harness`
  parameter runner.py's generalization requires. Scenario 1's assertions and
  acceptance-gate coverage must not change.
- .gitignore (node_modules/, pnpm store, npm cache, if not already covered)

Non-goals:
- No changes to the MCP Python SDK adapter, probes, or SCENARIO_REJECTED_CONNECT.
- No changes to SCENARIO_SHUTDOWN_DRAIN or any FdSocketProbe/behavioral-probe
  work; that remains a separate, un-checkpointed decision.
- No edits to suts/typescript-sdk once cloned and pinned.
- No GitHub writes: read-only `gh issue view` / `gh pr view` / `gh pr diff`
  only, to verify the citation and source the patch.
- No system-wide npm/pnpm install. pnpm runs via `npx pnpm@<pinned-version>`;
  its store and npm's own cache are pinned under the repo (Windows mount),
  never left to default to a home-directory or root-fs location.
- Root filesystem stays untouched: `df -h /` had ~5.8G free at last check.
  Every clone, node_modules, and cache directory must resolve under
  /run/media/Yatsuiii/Windows-SSD/raghav-research/shutdown-integrity.

Baseline: typescript-sdk#2023 read directly via `gh issue view` this session:
title "StdioClientTransport.close() does not kill the process tree, leaving
orphan processes", root cause is `ChildProcess.kill()` only signaling the
direct child PID, confirmed against `packages/client/src/client/stdio.ts` in
the SUT once cloned. Fixed control: PR #2024 ("fix: kill process tree on
StdioClientTransport.close()"), closed unmerged 2026-06-22, unconditional
fix (process-group kill on POSIX, `taskkill /T /F` on Windows), 7 new tests
including multi-level grandchild kill. A second candidate, PR #2596, makes the
same fix opt-in via a new `killProcessTree` option (default false) rather than
fixing close() unconditionally; #2024 is preferred as the fixed control
because it needs no adapter-side config to activate, matching how PR #3502
and PR #3218 were used as unconditional fixes in the prior scenarios.
Not yet checked this session: whether PR #2024's diff still applies cleanly
to typescript-sdk's current main (b654261, 2026-09-11) — verify before
declaring contract.verified=True and before relying on it as the fixed
control; if it has drifted, the citation is still valid but the patch needs
hand-adaptation, which must be flagged rather than silently forced.

Acceptance gates:
1. Scenario arms cleanly: FAIL against unpatched typescript-sdk main in 10/10
   runs, PASS against main+pr2024 in 10/10 runs, zero flakiness either
   direction (same bar as HANDOFF.md's scenario-1 gates, now applied
   cross-language).
2. The residual the FAIL trials catch is specifically the orphaned grandchild
   (the real MCP server process spawned through a wrapper), not the direct
   child, closing HANDOFF.md's still-open acceptance gate 2 on real SDK code.
3. Negative control (wrong trial tag) proven to trip the arming gate for this
   adapter too, not assumed to inherit from the Python adapter's proof.
4. The evidence bundle for one FAIL run contains residual PIDs with cmdlines,
   timings, and a working one-line repro, generated and verified the same way
   as the Python scenario's (Bash-executed, not eyeballed from source).
5. `ruff check src/` clean for the Python-side scenario declaration and any
   runner/sut changes. The Node adapter has no equivalent Python lint gate;
   note whatever the TS SDK's own lint/format config would flag, without
   necessarily running it (no contributor obligation here, just don't ship
   code that would visibly fail it).

Verification:
- `gh issue view 2023 --repo modelcontextprotocol/typescript-sdk` and
  `gh pr view 2024 --repo modelcontextprotocol/typescript-sdk` (done, see
  Baseline).
- `git apply --check` of the vendored patch against the pinned typescript-sdk
  commit, from a worktree, mirroring sut.py's existing pattern.
- `ruff check src/`.
- `pytest tests/` for the new adapter's arming-gate tests.
- `git status` shows only files in the allowed scope, plus suts/typescript-sdk
  (gitignored), node_modules and any pnpm store (gitignored).

Status: active
