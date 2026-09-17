"""Wires the TypeScript SDK adapter into the framework-free runner.

The scenario under test (typescript-sdk#2023) is entirely about
StdioClientTransport.close(): only packages/client differs between the
broken and fixed control. The fixture MCP server that gets wrapped is not
part of what is being tested, so it always imports from the stable, already
built `suts/typescript-sdk` checkout regardless of which control fixture's
client is under test that trial. Building packages/server per fixture would
be wasted work and would falsely suggest the server side varies too.
"""

import json
import shlex
from pathlib import Path

from shutdown_integrity.adapter import SubprocessAdapter
from shutdown_integrity.probes.base import Resource
from shutdown_integrity.scenario import ControlFixture
from shutdown_integrity.sut import REPO_ROOT, TS_SUT_CHECKOUT, PreparedNodeFixture, prepare_node

_HERE = Path(__file__).resolve().parent
ADAPTER_SCRIPT = _HERE / "adapter_main.mjs"
WRAPPER = _HERE / "fixtures" / "wrapper.mjs"
SERVER = _HERE / "fixtures" / "server.mjs"

NODE = "node"


class StdioCloseLeaksTreeHarness:
    """Harness for typescript-sdk#2023 (close() does not kill the process tree)."""

    adapter_id = "typescript-sdk"

    def prepare(self, fixture: ControlFixture) -> PreparedNodeFixture:
        return prepare_node(fixture)

    def launch(self, prepared: PreparedNodeFixture, trial_tag: str) -> SubprocessAdapter:
        return SubprocessAdapter(
            self.adapter_id,
            NODE,
            ADAPTER_SCRIPT,
            trial_tag,
            extra_env={"SHUTDOWN_INTEGRITY_SUT_ROOT": str(prepared.source_dir)},
        )

    def build_spec(self, prepared: PreparedNodeFixture) -> dict[str, object]:
        return {"command": NODE, "args": [str(WRAPPER), NODE, str(SERVER), str(TS_SUT_CHECKOUT)]}

    def residual_filter(self, resource: Resource) -> bool:
        """Tagged processes carrying SHUTDOWN_INTEGRITY_ROLE=server: the
        wrapper and the real MCP server it spawns, tagged by adapter_main.mjs.
        Excludes the adapter subprocess itself, which necessarily carries the
        trial tag too (to propagate it down) but is the harness, not the SUT.
        Unlike scenario 1, every remaining tagged resource is a violation:
        there is no legitimate keep-alive component to exclude. Anything
        still alive after close() returns is exactly what close()'s own
        contract (docs/get-started/first-client.md: "kills the process if it
        does not exit on its own") says should not exist.
        """
        return resource.detail.get("SHUTDOWN_INTEGRITY_ROLE") == "server"

    def repro_command(self, prepared: PreparedNodeFixture) -> str:
        """A literal, copy-pasteable command. Verified by hand against
        main-unpatched: the grep hits at t+1.5s, showing the fixture server
        (the orphaned grandchild) still running after close() returned.
        """
        spec = self.build_spec(prepared)
        request = shlex.quote(json.dumps({"op": "start_session", "spec": spec}))
        repro_adapter = ADAPTER_SCRIPT.relative_to(REPO_ROOT)
        launch = shlex.quote(f"(echo {request}; sleep 5) | node {repro_adapter}")
        return (
            f"SHUTDOWN_INTEGRITY_TRIAL=demo SHUTDOWN_INTEGRITY_SUT_ROOT={prepared.source_dir} bash -c {launch} & "
            f"sleep 1.5; ps -eo pid,ppid,cmd --no-headers | grep fixtures/server.mjs | grep -v grep; wait"
        )


STDIO_CLOSE_LEAKS_TREE_HARNESS = StdioCloseLeaksTreeHarness()
