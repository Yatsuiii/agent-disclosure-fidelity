# Session Contract

Objective: The discovery run. Both armed scenarios so far (mcp-py#3490,
ts#2023) are rediscoveries of bugs someone already filed; the instrument has
never been pointed at a codebase where nobody has. Confirm candidate targets
by local grep (not GitHub code search, which rate-limits inconsistently),
classify each as a discovery target (spawns its own processes) vs. an
inherited-behavior cell (delegates to a Python or TS MCP SDK), find whether
each target states a teardown contract at all, and only then build an
adapter and arm a scenario per confirmed target. Report a target x scenario
x verdict matrix with evidence bundles. File nothing anywhere.

Precommitted kill condition, binding: if four independent codebases yield
zero novel findings, that is the real answer, not a failure. It means the
bug class concentrates in shared dependencies (the MCP SDKs) rather than
scattering across projects that build on them, and this instrument is a
verifier, not a discovery engine, for that population. In that case stop,
say so plainly, and do not propose a fifth target to manufacture a finding.
The artifact becomes the methodology plus the Python/TypeScript divergence
result already in hand, not a new bug.

Branch: master

Parent: HEAD

Allowed files:
- .claude/SESSION_CONTRACT.md
- suts/** (new shallow clones only, gitignored already by the existing
  `suts/` pattern; read-only reference once cloned, never edited)
- src/shutdown_integrity/scenarios/discovery.py or scenarios/<target>.py
  (new: scenario declarations for confirmed discovery targets only)
- src/shutdown_integrity/adapters/<target>/** (new: one adapter subprocess
  plus harness per confirmed discovery target, reusing the existing
  AdapterHarness Protocol in runner.py unchanged)
- src/shutdown_integrity/runner.py (only if a genuinely new teardown_mode
  shape is needed that the existing ERROR_DURING_SETUP / graceful-close
  branches cannot express; prefer fitting the existing shapes)
- src/shutdown_integrity/sut.py: adds a `prepare_smithery_cli()` (or
  similarly named) function reusing the existing `_prepare_worktree` helper,
  for a single-package pnpm project run via `tsx` directly (no build step,
  unlike the TS SDK's tsdown-built packages). `prepare()` and `prepare_node()`
  and their existing callers are unchanged.
- patches/** (constructed fixed-control patches, named to say so, e.g.
  `constructed-<target>-process-group-teardown.patch`, distinct from
  upstream-sourced patches like pr3502/pr3218/pr2024)
- tests/test_discovery_<target>.py (new, mirroring test_arming_gate.py's
  shape: negative control, arm, evidence-bundle run)
- DISCOVERY.md (new: the target x scenario x verdict matrix and the
  contract-citation record per target; this is the step 4 report artifact)
- .gitignore (only if a new build-artifact directory needs covering)

Non-goals:
- No changes to the MCP Python or TypeScript SDK adapters, harnesses,
  scenarios, or their tests. Those two scenarios stay exactly as armed.
- No edits to any suts/<target> checkout once cloned.
- No GitHub writes anywhere: read-only `gh issue view` / `gh pr view` /
  `gh pr diff` / `gh api` only, for prior-art search and citation
  verification. No issues, comments, or pull requests, on any repo, ever,
  regardless of what a FAIL trial finds.
- No system-wide dependency installs. Per-target environments (venv, pnpm
  install+build) follow the exact pattern already proven in sut.py:
  isolated, cache pinned to the Windows mount, never touching root.
- Root filesystem stays untouched. `df -h /` had ~5.7G free at last check;
  every clone, venv, node_modules, and cache directory resolves under
  /run/media/Yatsuiii/Windows-SSD/raghav-research/shutdown-integrity.
- Do not arm a scenario whose contract citation is not verified=True against
  a primary source read this session. An unverified or invented expectation
  gets CONTRACT_UNCLEAR, never FAIL.
- Do not report a FAIL as novel without a prior-art search (issues AND pull
  requests, both open and closed) on that specific repo first.

Baseline: two prior checkpoints exist (commits 6962a9e, d25ba10). A third
checkpoint (DISCOVERY.md, staged not yet committed as this contract is
written) classified four candidates: adk-python and openai-agents-python are
PASS-by-delegation cells (both call the real, already-verified-correct
`mcp.client.stdio.stdio_client` directly); inspector was dropped (delegates
to the already-armed TS SDK, not novel); `arcadeai-labs/smithery-cli`
(formerly `smithery-ai/cli`, GitHub redirects the old name; confirmed via
`gh repo view`) hand-rolls its own spawn/close in `src/lib/uplink.ts` with no
stated contract, and a faithful line-cited reproduction (not the SUT's own
code, since the function is module-private) showed two real, prior-art-clear
observables: an orphaned grandchild after `close()` returns, and `close()`
itself burning its full 10s timeout budget instead of ~2-4s. Prior art
re-checked this session: issue #680 (mcp add/remove hangs on non-TTY stdin)
has an unrelated root cause (`inquirer.prompt` blocking, not the spawn/pipe
mechanism) — confirmed distinct, not a duplicate. Issue #779 is about
registry ID state, unrelated. The repo is active on issues (several filed in
September) but not merging contributions (PRs #791, #793, #798, #804, #811
all open since late June), which bounds how much to invest: this arming
effort is for the research artifact (an instrument finding something nobody
filed), not for a mergeable fix.

Objective for this stage: convert the smithery-cli finding from a
reproduction of extracted logic into either (a) a result that passes this
benchmark's own arming gate, driving the SUT's real, shipped, exported entry
point (`serveUplink`) through to the `close()` path, or (b) an explicit,
reportable methodological limit if that cannot be done within bounded effort.
A mock WebSocket server standing in for Smithery's cloud uplink relay is
required to reach `serveUplink` at all, since it is the only exported path
into `createStdioLocalPeer`.

Acceptance gates:
1. The mock relay drives the actual `serveUplink()` export (imported from
   the pinned checkout, not reimplemented) through `start()`, at least one
   message round-trip, and `close()`. If the mock cannot get the harness to
   call the SUT's real code by the stop condition below, stop and report the
   limit; do not force a partial mock into arming.
2. Control pair: broken control is the pinned commit as shipped. Fixed
   control is a constructed patch (spawn with `detached: true` on POSIX,
   `close()` signals the process group, mirroring
   `mcp/os/posix/utilities.py`'s `terminate_posix_process_tree`), named in
   its ControlFixture as constructed, not upstream-sourced, matching the
   pr3502/pr3218/pr2024 naming convention's opposite case.
3. Both observables measured, not just the residual: ProcessTreeProbe for
   the surviving grandchild, and `close()` wall-clock duration for the
   10s-vs-expected delta (the stronger, contract-independent signal, since
   it needs no stated guarantee to be visibly wrong).
4. If armed: unanimous broken/fixed across N trials, negative control proven
   to trip, evidence bundle with residual pids, cmdlines, timings, pinned
   commit, working repro. If not armed within the stop condition: DISCOVERY.md
   states plainly that arming was not reached, why, and that this is a
   reportable limit of the benchmark, not a hidden failure.
5. `ruff check src/` clean; no changes to the two already-armed scenarios.

Stop condition, binding: mocking a cloud relay can eat unbounded time. If the
mock cannot reach the real `close()` path within a bounded effort in this
session, stop and report the finding cannot be armed at this bar rather than
forcing a partial mock through. An arming gate that passed because the
harness faked the path under test is worse than no finding.

Verification:
- `ruff check src/`.
- `pytest tests/test_discovery_smithery_cli.py` if armed.
- `git status` shows only files in the allowed scope, plus suts/smithery-cli
  (already present, gitignored), any new .venvs/.worktrees/node_modules
  entries (gitignored).
- DISCOVERY.md's smithery-cli section updated in place with either the armed
  result or the stated limit, cross-checked against actual trial output.

Status: active
