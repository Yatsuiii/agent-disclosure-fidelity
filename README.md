# Shutdown Integrity Benchmark

Does an agent runtime SDK actually honour its session teardown contract?

After the SDK's documented close, shutdown, or failure path returns, this
benchmark checks whether any resource created by that session still exists, and
whether a later session can observe anything belonging to the earlier one.

Existing kill switch work (KILLBENCH, ControlBench) asks whether a misaligned
agent can be halted. This asks a layer down: whether the plumbing reliably
stops a cooperative one. If termination is unreliable under benign conditions,
that bounds what to expect under adversarial pressure.

Status: scaffolding. No measurements have been taken yet, and no result in this
repo should be cited until its scenario passes the arming gate described in
`DESIGN.md`.

- `DESIGN.md` architecture, integrity gates, threats to validity
- `HANDOFF.md` build brief for v1
