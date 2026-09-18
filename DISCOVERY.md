# Discovery run

Both scenarios armed before this run (mcp-py#3490, ts#2023) are rediscoveries
of bugs someone had already filed: that was structurally guaranteed, since
arming needs a known-broken control fixture, and known-broken means someone
already filed it. This run is the first time the instrument gets pointed at
codebases where nobody has. Precommitted kill condition (recorded in
`.claude/SESSION_CONTRACT.md` before any target was touched): if four
independent codebases yield zero novel findings, that is a real answer, not a
failure, and the run stops without a fifth target.

**Outcome: the kill condition does not fire.** Three of four candidates are
PASS-by-delegation or correctly dropped as not novel. The fourth,
`arcadeai-labs/smithery-cli` (formerly `smithery-ai/cli`; GitHub redirects the
old name, confirmed via `gh repo view`), is now **armed to this benchmark's
own bar**: FAIL 10/10 against unpatched main, PASS 10/10 against a
constructed process-group-teardown patch, negative control proven to trip,
driving the SUT's real, shipped, exported `serveUplink()` through a mock of
Smithery's cloud relay rather than a reimplementation of the code under test.
It remains reported as CONTRACT_UNCLEAR rather than FAIL, because no stated
teardown contract exists anywhere in the project — armed and CONTRACT_UNCLEAR
are orthogonal here: arming is about measurement rigor, CONTRACT_UNCLEAR is
about whether a maintainer ever promised the behavior this measures.

## Method note: why "armed" varies by row

Every armed scenario in this repo needs a broken/fixed control PAIR: without
a fixed control, an arming gate can prove a probe finds *something*, never
that it correctly distinguishes broken from fixed (DESIGN.md's arming-gate
reasoning). Three of the four targets below never reach that stage for
reasons specific to each, recorded in their own row rather than glossed over.

## Matrix

| Target | Spawns own processes? | Stated teardown contract? | Verdict | Armed? |
|---|---|---|---|---|
| google/adk-python | No (delegates to `mcp.client.stdio.stdio_client`) | N/A, inherited | PASS (by delegation) | No, source-verified |
| openai/openai-agents-python | No (delegates to `mcp.client.stdio.stdio_client`) | N/A, inherited | PASS (by delegation) | No, source-verified |
| modelcontextprotocol/inspector | No (delegates to `@modelcontextprotocol/client/stdio`) | N/A, inherited | Not novel, dropped | N/A |
| arcadeai-labs/smithery-cli (`uplink.ts`) | **Yes**, own `child_process.spawn` | No stated contract found | CONTRACT_UNCLEAR, armed | **Yes** |

## google/adk-python

Pinned commit `93f32d0b0026cd8b168a9c851875230be21ff731`.

**Classification (local grep, `git rev-parse HEAD` at clone time):
`src/google/adk/tools/mcp_tool/mcp_session_manager.py`** imports `stdio_client`
and `StdioServerParameters` from `...dependencies._mcp`, a one-file shim
(`src/google/adk/dependencies/_mcp.py`) that exists solely to resolve MCP SDK
version/naming drift between the public `mcp` package and Google's internal
mirror. It re-exports the real upstream symbols; it does not reimplement
them. `mcp_session_manager.py:1199` calls `stdio_client(server=...)` directly.
Other `Popen`/`create_subprocess_exec` hits in this repo
(`cli/dev_server.py`, `tools/bash_tool.py`, `environment/_local_environment.py`,
`code_executors/unsafe_local_code_executor.py`) are one-shot tool/dev-server
execution, not persistent MCP session transports, and are out of this
benchmark's scope (session lifecycle, not arbitrary subprocess use).

**Why this is a PASS cell, not a discovery target.** The actual process
spawn and its teardown are the SDK's own `stdio_client`, whose termination
path (`src/mcp/client/stdio.py` → `mcp/os/posix/utilities.py`,
`terminate_posix_process_tree`) was read directly against our own pinned
mcp-python-sdk checkout this session:

```
os.killpg(pgid, signal.SIGTERM)
... wait up to timeout_seconds, polling _group_alive(pgid) ...
os.killpg(pgid, signal.SIGKILL)  # if still alive
```

This signals the whole process group, not just the direct child; it is
exactly the fix shape that PR #2024 gave the TypeScript SDK for issue #2023.
`terminate_posix_process_tree` is confirmed live (imported and called at
`stdio.py:301`), not dead code.

**Beyond spawning:** ADK's own `create_session` (`mcp_session_manager.py`,
around line 1370) wraps session establishment in `AsyncExitStack` and closes
it on any exception (`except Exception: await exit_stack.aclose()`),
matching this project's own correct-invariant pattern from scenario 1. There
is a feature flag, `_MCP_GRACEFUL_ERROR_HANDLING`, gating an *additional*
check for a dead background task even when the read/write streams look open,
with a code comment describing exactly the failure mode it guards
("a crashed transport can leave the session's read/write streams open even
though the underlying task has already died") — direct evidence the ADK team
has already iterated on this defect class, consistent with the open issue
#7109 already in HANDOFF.md's own research.

**Not independently re-verified with a live trial against ADK's own code.**
This PASS cell rests on tracing delegation to already-verified SDK behavior
and reading ADK's own exit-stack handling, not on running ADK itself.
Building a full ADK adapter (google-auth and its dependency tree) to
re-confirm what the shared dependency already proves was judged low
information gain for the effort, per this session's time budget. If a live
ADK-specific trial is wanted later, `mcp_session_manager.py:1199`'s
`stdio_client()` call is the entry point to instrument.

**Caveat:** `pyproject.toml` pins `mcp>=1.24,<3`, a wide floor. This
PASS-by-delegation claim is about the *architecture* (correctly deferring
process lifecycle to the SDK) at the pinned SDK version this benchmark
tests, not a guarantee about what an old resolved `mcp==1.24` actually does.

## openai/openai-agents-python

Pinned commit `e34311b973cb37dae72920fb70cbcd7b35b8fa4b`. Same shape, same
conclusion, checked independently rather than assumed from the ADK read.

**Classification:** `src/agents/mcp/server.py:20` imports `ClientSession`,
`StdioServerParameters`, and `stdio_client` directly from `mcp` — no shim, no
reimplementation. Other spawn-shaped hits in this repo
(`extensions/experimental/codex/exec.py`, `sandbox/sandboxes/unix_local.py`)
are sandboxed code execution, not MCP session transports.

**Exit-stack handling:** `MCPServerStdio.connect()` (`server.py:1336`) wraps
session establishment in `self.exit_stack.enter_async_context(...)` inside a
`try`/`except BaseException`, and on failure calls `self.cleanup()` (which
calls `self.exit_stack.aclose()`) before re-raising — the same
teardown-on-setup-failure invariant scenario 1's citation is built on. A code
comment even references "a known issue with the MCP library's async
generator cleanup," again showing direct engagement with this defect class.

**Caveat:** `pyproject.toml` pins `mcp>=1.19.0,<3`, wider still than ADK's
floor. Same architectural-PASS, not-version-pinned-guarantee caveat applies.

## modelcontextprotocol/inspector

Pinned commit `2e90a628e6296c62e4bef942afbb43d3faa4baf4`.

**Classification:** `core/mcp/node/transport.ts:11` imports
`StdioClientTransport` from `@modelcontextprotocol/client/stdio` — the exact
package this repo already built an adapter for and armed against issue
#2023. Per the run's own instruction ("if through the SDK it is #2023
inherited and not a target"), this is dropped without further work: a FAIL
here would report the identical bug already recorded in this repo's own
`ts/stdio-close-leaks-process-tree` scenario, not a new one.

## arcadeai-labs/smithery-cli — `uplink.ts`'s `createStdioLocalPeer`

Repo renamed from `smithery-ai/cli` to `arcadeai-labs/smithery-cli`; GitHub
redirects the old name transparently (`gh repo view smithery-ai/cli` resolves
to it), so every prior-art search below against the old name did hit the
current repo.

**Classification:** confirmed a genuine discovery target by local grep and
direct source read, pinned commit `407ac3b33944a585357379bc213fdf1ee55464d7`.
`src/lib/uplink.ts` imports `spawn` from `node:child_process` directly and
implements its own JSON-RPC stdio framing using only the SDK's low-level
`ReadBuffer`/`serializeMessage` helpers (`@modelcontextprotocol/sdk/shared/stdio.js`)
— it does not import or use `StdioClientTransport` at all for this path. This
is Smithery's "uplink" feature: relaying a locally-spawned MCP server to
Smithery's cloud service (`uplink.smithery.run`) over WebSocket, for `smithery
mcp add` and `smithery mcp add-uplink-bundle`. Confirmed live and reachable
(not dead code): `serveUplink` is called from `commands/mcp/add.ts` and
`commands/mcp/add-uplink-bundle.ts`, both of which have their own test files.

**Contract search, before any measurement (per this run's own step 2 rule):**
no doc comment on `close()` or the `LocalPeer` interface it implements; no
README or docs file mentioning process cleanup for `uplink`; the test file
covering this path (`src/lib/__tests__/uplink.test.ts`) mocks the peer
entirely (`async close() {}`) and asserts nothing about spawned-process
behavior. The changelog records a `cleanupChildProcess` utility that was
"created for consistent process cleanup across commands" including `uplink`
— but that utility, and the `dev`/`playground` commands it served, no longer
exist in the current tree; `uplink.ts`'s current `close()` is a self-contained
kill sequence with no shared utility involved. This looks like it may be a
regression from a since-removed refactor rather than a contract this file
ever satisfied on its own, but that is inference from a changelog entry, not
a citable current-state fact, so it is not the basis for the verdict below.
The two `detached: true` usages elsewhere in this codebase
(`commands/homepage.ts:202`, `commands/mcp/deploy.ts:240`) are for the
opposite purpose — deliberately daemonizing a background process so it
survives the CLI exiting, via `child.unref()` — not evidence of a
process-group-kill invariant this file fails to follow.

**Verdict: CONTRACT_UNCLEAR.** No stated contract survives this search, so
per this run's own rule ("no stated contract means the honest verdict is
CONTRACT_UNCLEAR, not FAIL"), this cannot be reported as a confirmed FAIL
against a maintainer-owned expectation, regardless of what the structural
evidence below shows.

**Structural evidence (real, not source-only).** `createStdioLocalPeer` is
module-private (not exported), and `serveUplink` — the exported entry point —
requires a live WebSocket connection to Smithery's uplink relay to reach it,
which this session judged out of scope to mock. Building and running a
faithful, line-cited reproduction of the two functions that matter instead
of resting on a source read:

```js
// Reproduces uplink.ts:591-598 (spawn options) and uplink.ts:636-655
// (close()), verbatim, against pinned commit 407ac3b3.
const child = spawn(command, args, {
    cwd: process.cwd(),
    env: { PATH: process.env.PATH, SHUTDOWN_INTEGRITY_TRIAL: tag },
    stdio: ['pipe', 'pipe', 'inherit'],
    shell: false,
});
// ... close(): stdin.end(), wait up to 5s, kill('SIGTERM'), wait up to 5s,
// kill('SIGKILL') if still alive — no `detached`, no process-group signal.
```

Run against this repo's own `wrapper.mjs` + `server.mjs` fixtures (already
built and verified for the TypeScript SDK scenario; `wrapper.mjs` stands in
for a real `npx`/`uvx` wrapper, spawning a child with genuine fd inheritance;
`server.mjs` keeps a `setInterval` alive so it does not exit merely because
its stdin reaches EOF, matching real-world MCP servers with background work):

```
spawned 14811                          # the wrapper (the direct child)
close() returned after 10.008396939 s  # both 5s waits fully elapsed
```

Residual immediately after `close()` returned, tag `smithery-repro2`:

```
pid=14818  ppid=1013 (reparented away from 14811, the dead wrapper)
cmdline=/usr/bin/node .../fixtures/server.mjs .../suts/typescript-sdk
```

The direct child (14811, the wrapper) is correctly killed. The grandchild
(14818, the real MCP server) survives, reparented off its dead parent —
exactly typescript-sdk#2023's shape, independently reimplemented. A second,
smaller finding falls out of the same run: `close()` itself takes the full
10s (both timeout windows) rather than the ~2-4s scenario 1 and the TS
scenario show, because Node's `'close'` event on the wrapper's `ChildProcess`
object waits for its stdio streams to fully close, and the still-alive
grandchild holds the inherited stdout pipe open — so even the part of
`close()` that does work (killing the direct child) is silently slower than
intended whenever a wrapper is involved.

**Prior art search (this run's step 4, done before writing this row, then
independently re-run and cross-checked):**
`gh issue list --repo smithery-ai/cli --state all --search "<orphan|zombie|kill|process tree|uplink close|uplink|leak|child process>"`
— zero results across every query. Two adjacent hits found on re-check and
read directly, neither a match:

- **#680**, "mcp add/remove commands hang indefinitely when stdin is not a
  TTY and target client is running." Read in full: root cause is
  `promptForRestart()` (`src/utils/client.ts`) calling `inquirer.prompt`
  unconditionally when the target client is running, with no TTY check —
  an interactive-prompt hang, unrelated to spawn, pipe inheritance, or
  `close()`. Confirmed distinct mechanism, not a duplicate of either
  observable below.
- **#779**, "Orphaned ID locked after failed initial scan." Contains the word
  "orphaned" but is about registry ID state, not processes. Unrelated.

No open or closed issue or PR on this repo covers either observable below.

**Now armed to this benchmark's own bar.** Driving the SUT's real, shipped,
exported entry point, not a reimplementation: `serveUplink()`
(`src/lib/uplink.ts`) is the only exported path into the module-private
`createStdioLocalPeer`, and it requires a paired WebSocket connection to
Smithery's cloud uplink relay before it runs at all. This session read
`pairUplinkSocket()` and `serveUplink()`'s own call order directly and found
two facts that make a lightweight mock sufficient rather than a full relay
reimplementation:

1. `getUplinkPairingEndpoint()` (`uplink.ts:670`) already honours
   `SMITHERY_UPLINK_BASE_URL` as an override — a real hook the SUT's own code
   provides, not one this benchmark invented.
2. `serveUplink()`'s own body runs `await local.start()` (the real spawn plus
   a real MCP `initialize`/`notifications/initialized` handshake against the
   child, per `wrapInitialized`) **before** it ever pairs the socket
   (`uplink.ts:308-312`). A mock that only accepts the WebSocket upgrade is
   therefore enough: by the time it sees a connection, the shipped
   local-spawn code has already fully run.

The adapter (`src/shutdown_integrity/adapters/smithery_cli/`) runs the SUT's
own TypeScript source directly via `tsx` (matching how the SUT's own test
suite imports `uplink.ts`, e.g. `src/lib/__tests__/uplink.test.ts`, including
polyfilling the same `__SMITHERY_VERSION__` global that test file polyfills,
an esbuild `--define` this benchmark does not reproduce independently), spins
up an in-process mock relay (`fixtures/mockRelay.mjs`) that accepts any
WebSocket upgrade and does nothing else, and delivers teardown as a real
`SIGTERM` to its own process — exactly how a user's Ctrl-C or a process
manager's shutdown signal reaches `serveUplink()`, which registers
`process.on("SIGTERM", ...)` itself (`uplink.ts:196`).

**Control pair.** Broken control is the pinned commit as shipped
(`smithery-cli-main-unpatched`). Fixed control
(`smithery-cli-constructed-process-group-teardown`) is constructed, not
upstream-sourced — no fix PR exists to source one from, and the repo is not
merging contributions regardless (PRs #791, #793, #798, #804, #811 all open
since late June) — mirroring `mcp/os/posix/utilities.py`'s
`terminate_posix_process_tree` in Node idiom: spawn with `detached: true` on
POSIX, `close()` signals the whole process group (`process.kill(-pid,
signal)`), polling with a signal-0 probe the same way the Python side does,
since a group only disappears once every member is dead and reaped. Diff at
`patches/constructed-smithery-cli-process-group-teardown.patch`.

**Arming result** (`pytest tests/test_discovery_smithery_cli.py`, all 4
tests pass):

- FAIL 10/10 against unpatched main, PASS 10/10 against the constructed
  patch, zero flakiness either direction.
- Negative control (wrong trial tag, run against the broken fixture) proven
  to trip the gate rather than falsely report PASS.
- Residual filtering (`SHUTDOWN_INTEGRITY_ROLE=server`, set on the spawned
  target's env) correctly excludes the adapter's own `tsx`/esbuild-service
  processes, which also carry the trial tag (needed to propagate it down)
  but are the harness, not the SUT.

**Both observables measured, as the arming task asked, not just the
residual:**

1. **Structural**: one representative broken-control trial —
   `teardown_return_s: 10.011`, residual `pid=21096`,
   `cmdline=node .../fixtures/server.mjs .../suts/typescript-sdk` (the real
   MCP server, the grandchild, not the wrapper — closing the same
   grandchild-vs-direct-child distinction HANDOFF.md's acceptance gate 2
   asked for, now proven a third time on a third independent codebase). The
   matching fixed-control trial: `teardown_return_s: 5.016e-06`... `residuals:
   ()`, `settle_s` effectively `0`.
2. **Duration, the stronger, contract-independent signal**: `close()` itself
   takes the full ~10s (both `STDIO_KILL_TIMEOUT_MS` windows) on unpatched
   code versus ~5s on the constructed fix, because Node's `'close'` event on
   the direct child's `ChildProcess` object waits for its stdio streams to
   fully close, and the still-alive grandchild holds the inherited stdout
   pipe open. This needs no stated contract to be visibly wrong: any caller
   of `serveUplink()` (a human waiting on `smithery mcp add`, or a script
   spawning it non-interactively) observes a doubled shutdown delay whether
   or not they know why, which is what makes this filable at all given the
   CONTRACT_UNCLEAR verdict above.

## Kill condition outcome

Does not fire. One candidate (smithery-cli) produced a real, prior-art-clear
finding, now armed to this benchmark's own bar: driving the SUT's real,
shipped, exported code through a mock of its cloud relay dependency, with a
constructed control pair, a negative control proven to trip, and both a
structural observable (the orphaned grandchild) and a contract-independent
one (the doubled `close()` duration). It is reported at CONTRACT_UNCLEAR
rather than FAIL, because no stated teardown contract exists anywhere in the
project — that is a fact about the target, not a limitation of the
measurement, and this benchmark's own rules keep the two distinct rather than
collapsing "we measured it rigorously" and "a maintainer promised this" into
one verdict.

## Filed

Nothing. No issues, comments, or pull requests were opened on any repository
in this run, per the session's own non-goals.
