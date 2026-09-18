"""Wires the smithery-cli adapter into the framework-free runner.

Unlike the SDK adapters, the target under test (createStdioLocalPeer, inside
uplink.ts) is module-private: there is no exported entry point that calls it
directly except `serveUplink()`, which needs a paired WebSocket connection to
Smithery's cloud uplink relay before it runs at all. The adapter mocks that
relay in-process (fixtures/mockRelay.mjs) rather than reimplementing the
function under test, which is what makes this an arming of the real shipped
code rather than a reproduction of extracted logic (see DISCOVERY.md).
"""

from pathlib import Path

from shutdown_integrity.adapter import SubprocessAdapter
from shutdown_integrity.probes.base import Resource
from shutdown_integrity.scenario import ControlFixture
from shutdown_integrity.sut import REPO_ROOT, PreparedNodeFixture, prepare_smithery_cli

_HERE = Path(__file__).resolve().parent
ADAPTER_SCRIPT = _HERE / "adapter_main.mjs"

_TS_FIXTURES = REPO_ROOT / "src" / "shutdown_integrity" / "adapters" / "typescript_sdk" / "fixtures"
WRAPPER = _TS_FIXTURES / "wrapper.mjs"
SERVER = _TS_FIXTURES / "server.mjs"
_TS_SUT_ROOT = REPO_ROOT / "suts" / "typescript-sdk"

NODE = "node"


class UplinkStdioLeaksTreeHarness:
    """Harness for the smithery-cli discovery finding (uplink.ts's
    createStdioLocalPeer: hand-rolled spawn/close, no stated contract).
    """

    adapter_id = "smithery-cli"

    def prepare(self, fixture: ControlFixture) -> PreparedNodeFixture:
        return prepare_smithery_cli(fixture)

    def launch(self, prepared: PreparedNodeFixture, trial_tag: str) -> SubprocessAdapter:
        tsx = prepared.source_dir / "node_modules" / ".bin" / "tsx"
        return SubprocessAdapter(
            self.adapter_id,
            tsx,
            ADAPTER_SCRIPT,
            trial_tag,
            extra_env={"SHUTDOWN_INTEGRITY_SUT_ROOT": str(prepared.source_dir)},
        )

    def build_spec(self, prepared: PreparedNodeFixture) -> dict[str, object]:
        # Reuses the TypeScript SDK scenario's own fixtures: wrapper.mjs
        # (a faithful npx/uvx stand-in, spawns a child with genuine fd
        # inheritance) and server.mjs (keeps a setInterval alive so it does
        # not exit merely from stdin EOF), both already proven correct
        # there. Tagged with SHUTDOWN_INTEGRITY_ROLE=server so
        # residual_filter can tell the spawned target apart from the
        # adapter's own tsx/esbuild-service processes, which also carry the
        # trial tag (needed to propagate it down) but are the harness, not
        # the SUT.
        return {
            "command": NODE,
            "args": [str(WRAPPER), NODE, str(SERVER), str(_TS_SUT_ROOT)],
            "env": {"SHUTDOWN_INTEGRITY_ROLE": "server"},
        }

    def residual_filter(self, resource: Resource) -> bool:
        return resource.detail.get("SHUTDOWN_INTEGRITY_ROLE") == "server"

    def repro_command(self, prepared: PreparedNodeFixture) -> str:
        """Not a plain shell one-liner like the SDK scenarios': this target
        has no public entry point short of the full mock-relay dance, so the
        working repro is the adapter script itself, run the same way the
        arming trials run it.
        """
        tsx = Path(prepared.source_dir / "node_modules" / ".bin" / "tsx").relative_to(REPO_ROOT)
        rel_adapter = ADAPTER_SCRIPT.relative_to(REPO_ROOT)
        return (
            f"SHUTDOWN_INTEGRITY_SUT_ROOT={prepared.source_dir} SHUTDOWN_INTEGRITY_TRIAL=demo {tsx} {rel_adapter} "
            f'<<< \'{{"op": "start_session", "spec": {{"command": "node", "args": '
            f'["{WRAPPER}", "node", "{SERVER}", "{_TS_SUT_ROOT}"], "env": {{"SHUTDOWN_INTEGRITY_ROLE": "server"}}}}}}\' '
            f"# then send teardown on the same stdin, and check "
            f"'ps -eo pid,ppid,cmd | grep fixtures/server.mjs' before it exits"
        )


UPLINK_STDIO_LEAKS_TREE_HARNESS = UplinkStdioLeaksTreeHarness()
