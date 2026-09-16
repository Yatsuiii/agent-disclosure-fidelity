# Handoff: build v1 of the Shutdown Integrity Benchmark

You are picking this up cold. Everything you need is in this repo. Read
`DESIGN.md` in full before writing code: it contains the architecture and the
reasoning behind the parts that look over-engineered but are not.

## Why this exists

Raghav found and fixed a real session isolation bug in `cmcp` (issue 625, PR
634): `rebind_session()` rotated the audit chain but never called `aclose()`,
so the stdio child process, pooled HTTP clients, and provenance caches survived
a session close and were reused by the next session. Cross-session
contamination, in a runtime built for compliance-sensitive deployments.

A survey of other agent runtime projects found the same *class* of bug
everywhere, currently open:

- `modelcontextprotocol/python-sdk#3490` rejected connect leaves its transport running
- `modelcontextprotocol/python-sdk#2150` active sessions not terminated during shutdown
- `modelcontextprotocol/python-sdk#2958` CLOSE_WAIT socket accumulation
- `modelcontextprotocol/python-sdk#1691` open request for an explicit session lifecycle state machine
- `modelcontextprotocol/typescript-sdk#2023` close() does not kill the process tree, orphans survive
- `modelcontextprotocol/typescript-sdk#2002` zombie accumulation on stdin close
- `modelcontextprotocol/typescript-sdk#343` (closed) one user's notification delivered to another user
- `google/adk-python#7109` delete_session leaves copied state with no removal path

Nobody has systematically audited real agent runtime SDKs against this failure
class. That audit is the artifact. It is aimed at three things at once: an eval
methodology pitch (Mercor research fellowship), a concrete AI safety audit
(grantmaking.ai, corrigibility and safe interruptibility framing), and
eventually a certification tool (startup wedge).

**The benchmark is the original contribution, not any single bug fix.** Do not
get pulled into just fixing known bugs: rebasing someone else's closed PR
proves nothing. The value is the instrument, and whatever previously
undocumented failures the instrument finds.

## Where things are

- Repo root: `/run/media/Yatsuiii/Windows-SSD/raghav-research/shutdown-integrity`
- System under test: `suts/mcp-python-sdk`, pinned at commit
  `9972c21aa42054fb1450c5fc614761ed11847ec6`, verified identical to `origin/main`
  as of 2026-09-16. Gitignored, reclone if missing.
- Control fixture patch: `patches/pr3502-close-rejected-transport.patch`
- Scenario declarations: `src/shutdown_integrity/scenarios/mcp_python.py`

**Work on the Windows partition, not the Linux root filesystem.** Root is at
90 percent with roughly 6 GB free and a plain dependency install can hit
ENOSPC. The Windows mount has tens of GB free. Check `df -h` before anything
that writes significant data.

## Hard constraints

- **Session contract.** A global hook blocks edits unless
  `.claude/SESSION_CONTRACT.md` exists, is complete, and matches the current
  branch. The contract currently describes the scaffolding session and is
  marked `Status: active`. **Update it for your own objective before editing
  anything**, including your own allowed file scope and acceptance gates.
- **No dependency installs** unless your contract explicitly authorises them.
  `psutil` is declared in `pyproject.toml` but deliberately not installed.
- **No em dashes** anywhere: code, comments, commit messages, docs. Use
  periods, commas, or spaced hyphens.
- **APOSD discipline.** Deep modules, simple interfaces, no shallow
  pass-throughs. Comments explain why, never what. A PostToolUse hook runs
  ruff on every edited Python file and blocks on unused imports or functions
  over complexity 10.
- **No GitHub writes.** No issues, no comments, no pull requests, no pushes,
  from this work, without Raghav explicitly authorising that specific action.

## Facts already verified, do not re-derive

**Root cause of #3490.** In `src/mcp/client/session_group.py`,
`_establish_session()` registers the session's transport into the group level
exit stack as soon as `initialize()` succeeds. `connect_to_server()` then calls
`connect_with_session()` which calls `_aggregate_components()`, which raises
`MCPError` on a name collision across servers. That raise happens *after* the
transport is live and registered, and nothing catches it, so a caller who sees
`connect_to_server()` raise assumes no connection was made while the stdio
child process keeps running until the whole group eventually closes. Note that
`_establish_session` already maintains the correct invariant for failures
during its own setup (`except Exception: await session_stack.aclose(); raise`),
which is why the missing cleanup in the caller is a contract violation rather
than a matter of opinion.

**The fix shape** is in `patches/pr3502-close-rejected-transport.patch`: wrap
the `connect_with_session()` call, pop the session's exit stack, `aclose()` it,
re-raise. It ships with a regression test. It was auto-closed by a bot, never
rejected on merit. **Use it as the fixed control fixture. Do not submit it.**

**The MCP Python SDK repo auto-closes pull requests** from contributors not
assigned to the linked issue by a maintainer. Getting assigned comes before
writing a fix, whenever fixes eventually happen.

**The SDK is `anyio` based** and heavily built on async context managers and
`contextlib.AsyncExitStack`. Adapters must respect that rather than fighting it.

## Your first task

Build the arming gate plus scenario 1 (`mcp-py/rejected-connect-leaks-transport`)
end to end. Nothing else. Specifically:

1. A minimal MCP Python adapter subprocess implementing the control protocol in
   `src/shutdown_integrity/adapter.py`, derived from the SDK's own documented
   usage example (record which example in a comment, so findings cannot be
   dismissed as unrealistic usage).
2. `ProcessTreeProbe` with environment tag attribution, walking descendants.
3. The trial runner: tag, baseline, run, poll to deadline, N repeats,
   unanimity aggregation.
4. The arming gate wired so an unarmed scenario can only report INCONCLUSIVE.

### Acceptance gates for your work

1. Scenario 1 arms cleanly: FAIL against unpatched `main` in 10 of 10 runs,
   PASS against `main` plus `patches/pr3502-...` in 10 of 10 runs. Zero
   flakiness in either direction.
2. The probe detects a residual grandchild, not only a direct child. Prove it
   with a fixture that spawns the server through a wrapper such as `sh -c`.
3. Deliberately break the probe (point it at the wrong tag) and confirm the
   arming gate catches it and refuses to report a verdict. A gate that has
   never been shown to trip is not a gate.
4. `ruff check src/` clean, and the evidence bundle for one FAIL contains
   residual PIDs with cmdlines, timings, and a working one line repro.

## Do not

- Do not file issues or open pull requests. Findings go to Raghav for triage.
- Do not widen to a second SDK before scenario 1 arms cleanly.
- Do not use mocks for the probes. Mocked teardown re-proves what the SDK's own
  unit tests already assert and would make the whole exercise worthless.
- Do not trust a green run. A test that has not been shown to fail against a
  known-broken fixture has proven nothing, and four false readings in an
  earlier session all came from broken probes rather than broken code.
- Do not sleep then assert. Poll with a deadline.
- Do not report a result whose scenario is unarmed, or whose contract citation
  is still marked `verified=False`.
