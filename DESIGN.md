# Shutdown Integrity Benchmark: architecture

## What this measures

Whether an agent runtime SDK actually honours its session teardown contract.
After the SDK's documented close, shutdown, or failure path returns, does any
resource created by that session still exist, and can a later session observe
anything belonging to the earlier one.

This is deliberately the infrastructure layer, not the behavioural layer.
Existing work (KILLBENCH, ControlBench) asks whether a misaligned agent can be
halted. This asks whether the plumbing underneath reliably stops a cooperative
one. If termination is unreliable under benign conditions, that is a lower
bound on what to expect under adversarial pressure.

## Two foundational decisions

### The runner never imports the SDK under test

Every framework is driven out of process through a thin adapter subprocess
speaking newline-delimited JSON. This buys four things at once:

- language independence: a Node adapter looks identical to a Python one,
- crash isolation: a hung or crashed adapter does not take down the run,
- a correct vantage point: process and descriptor state is observed from
  outside the process being measured,
- no self-contamination: the runner's own event loop and garbage collector
  stay out of the measurement.

The cost is a small control protocol. It is worth it.

### Two assertion modalities

**Structural**: after teardown returns, does resource X still exist. A live
process, a socket parked in CLOSE_WAIT, a task still scheduled.

**Behavioural**: can session B observe something belonging to session A. B's
request served by A's child process, A's cached credential reused by B, A's
response delivered to B.

Structural catches leaks earlier and automates more cleanly. Behavioural is the
stronger evidence for the safety framing, because "B can see A's state" is the
isolation failure itself rather than a proxy for it. MCP typescript-sdk issue
343, where one user's notification was delivered to another user, is purely
behavioural. No structural probe would ever have caught it.

## Layers

```
Scenario layer      declarative cases: lifecycle script, contract citation,
(framework-free)    invariants, control fixtures, known-issue refs
        |
Adapter layer       adapter subprocess, JSON control protocol
(per SDK, per lang) start_session / exercise / teardown(mode) / rebind
                    plus capability declaration
        |
Execution layer     trial runner: sandbox, tagging, baseline, N repeats,
                    deadline polling, crash safety
        |
Probe layer         ProcessTreeProbe, FdSocketProbe, behavioural probing
        |
Verdict layer       arming gate, tri-state verdict, evidence bundle
```

The adapter surface is deliberately tiny so that adding a framework is a day of
work rather than a month:

- `declare_capabilities()`
- `start_session(spec) -> handle`
- `exercise(handle)`, one real tool call, so the session is genuinely live
  rather than merely constructed
- `teardown(handle, mode)`
- `rebind(handle)`

Teardown *mode* is a first class axis because every bug in the taxonomy lives
in a non-happy path. Testing only graceful close finds nothing.

## Three integrity gates

These are what separate this from a leak detector that occasionally lies.

### 1. Arming

Every scenario ships as a triple: the test, a known-broken fixture, a
known-fixed fixture. A scenario is armed for an adapter only if it fails
against broken and passes against fixed, unanimously across N runs. An unarmed
scenario may report INCONCLUSIVE and nothing else.

This gate exists because **a harness bug and a real finding are
indistinguishable from the outside**. A probe reading the wrong PID namespace
fails against everything, which looks exactly like finding a leak everywhere. A
probe that silently returns nothing passes against everything, which looks
exactly like a clean SDK. Only the controls tell them apart, so the gate runs
in both directions.

For the MCP Python SDK the controls come free and externally sourced:
unpatched `main` is the broken fixture, `main` with PR 3502 applied is the
fixed one. Controls that came from the project rather than from the benchmark
author are much harder to argue with.

### 2. Attribution

Trials tag spawned processes through an inherited environment variable
(`SHUTDOWN_INTEGRITY_TRIAL`), and attribution reads the environment rather than
walking PID ancestry.

This is load bearing, not cosmetic. **An orphaned grandchild is reparented to
PID 1 the moment its parent dies**, which destroys ancestry based attribution
in precisely the case the benchmark exists to detect. An ancestry-only probe
would silently miss the wrapper orphan bug (npx, uvx, sh -c) while appearing to
work correctly. Environment is inherited down the entire tree and survives
reparenting. PID ancestry stays as a cross-check only.

### 3. Determinism

No sleep-then-assert, anywhere. Every check is poll-with-deadline. Each
scenario runs N times (default 10) and reports only on unanimity. A split
result is FLAKY, which is a reportable verdict rather than something to retry
until green: teardown that works seven times out of ten is itself a finding,
and arguably a more alarming one than a clean failure. The full timing
distribution is kept, so a writeup can say "residual present in 10/10 trials,
still alive at the 30s deadline" instead of a bare boolean.

## Verdicts

`PASS`, `FAIL`, `FLAKY`, `INCONCLUSIVE` (unarmed), `NOT_APPLICABLE`
(capability not declared), `CONTRACT_UNCLEAR`.

`NOT_APPLICABLE` is a benchmark integrity concern. If a framework that lacks
`rebind` scored PASS on rebind leak scenarios, the benchmark would reward
missing functionality over functionality that exists and is slightly wrong.
Capability declaration plus an explicit NOT_APPLICABLE prevents that inversion.

## Flow

1. **Arm.** Run both control fixtures. Quarantine unarmed scenarios before any
   real measurement happens.
2. **Baseline.** Snapshot ambient processes and descriptors so trial deltas are
   computable.
3. **Trial**, repeated N times. Fresh sandbox and trial tag, `start_session`,
   `exercise`, `teardown(mode)`, wait for the teardown call to *return* (the
   contract boundary at which the SDK has claimed it is finished), then poll
   probes to the deadline.
4. **Behavioural pass**, for isolation scenarios. After A's teardown, start
   session B in the same adapter process and probe whether B can observe A's
   artifacts.
5. **Verdict.** Aggregate, gate, attach an evidence bundle: residual PIDs with
   cmdlines and environment tags, socket states, timing distribution, a one
   line repro command, the pinned SUT commit, the environment fingerprint.
6. **Triage.** A FAIL on a scenario carrying no known-issue ref is a *candidate*
   novel finding, routed to manual review. It is never auto-filed. Filing a
   false positive against a major open source project would damage exactly the
   credibility this work exists to build.

## Threats to validity

Belongs in the writeup, not only in the code.

- **Container reaping produces false negatives.** A container with a proper
  init subreaper reaps orphans promptly, so the harness sees no leak where a
  developer machine would see one linger indefinitely. The environment
  fingerprint is therefore load bearing, and findings should be confirmed in
  both environments before being called real.
- **Deferred cleanup is not a leak.** Report "gone but slow" separately from
  "never gone", with timings attached.
- **Ambiguous contracts** get CONTRACT_UNCLEAR, which is itself worth filing as
  a spec question rather than as a bug.
- **Version drift.** Pin the exact SUT commit for every run.

## Known weak point

Structural detection of in-process object leaks (surviving caches, pooled
clients, the cmcp issue 625 class) is genuinely hard across a subprocess
boundary. For v1 that category is covered **behaviourally only**, and the
writeup must say so plainly. Under-claiming coverage is much cheaper than
shipping a probe that quietly returns empty and reads as PASS.

## Open design questions

1. **Behavioural probe interface.** Behavioural checks do not fit the
   `Probe.snapshot` shape, since they drive a second session rather than
   enumerate resources. Whether they belong as an adapter op, a distinct
   protocol, or a scenario level script is unresolved.
2. **Sandboxing strength.** Environment tagging handles attribution. Whether
   trials additionally need a dedicated PID namespace (via `unshare`) to avoid
   cross-trial interference under parallel execution is untested.
3. **Adapter fidelity.** An adapter that uses the SDK in a way no real user
   would makes findings easy to dismiss. Adapters should mirror the SDK's own
   documented usage examples, and the writeup should say which example each
   adapter was derived from.

## v1 scope

One framework (MCP Python SDK), the two scenarios declared in
`scenarios/mcp_python.py`, both controls, full rigor, unanimity across 10 runs.
Prove the machine works before widening. Then add the TypeScript adapter, which
is what substantiates the cross-language claim. Then a third framework for the
cross-ecosystem claim.

Two expectations to set honestly. This is a multi-week build at real rigor, not
a weekend. And a novel finding is not guaranteed: the harness may only
rediscover known issues, in which case the contribution is the methodology and
the cross-SDK matrix rather than a new bug.
