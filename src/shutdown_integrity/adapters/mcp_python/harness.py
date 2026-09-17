"""Wires the MCP Python SDK adapter into the framework-free runner.

Extracted from what used to be inline in runner.py: the adapter script path,
the two fixture servers, how to build a start_session spec for them, which
tagged residuals actually count as a violation, and a working one-line repro.
This is the only file scenario 1's runner behavior depends on beyond
runner.py itself; adapter_main.py, the fixtures, and scenarios/mcp_python.py
are unchanged from the session that first armed this scenario.
"""

import json
import shlex
from pathlib import Path

from shutdown_integrity.adapter import SubprocessAdapter
from shutdown_integrity.probes.base import Resource
from shutdown_integrity.scenario import ControlFixture
from shutdown_integrity.sut import REPO_ROOT, PreparedFixture, prepare

_HERE = Path(__file__).resolve().parent
ADAPTER_SCRIPT = _HERE / "adapter_main.py"
LIBRARY_SERVER = _HERE / "fixtures" / "library_server.py"
WEB_SERVER = _HERE / "fixtures" / "web_server.py"


class RejectedConnectHarness:
    """Harness for mcp-py/rejected-connect-leaks-transport (issue #3490)."""

    adapter_id = "mcp-python"

    def prepare(self, fixture: ControlFixture) -> PreparedFixture:
        return prepare(fixture)

    def launch(self, prepared: PreparedFixture, trial_tag: str) -> SubprocessAdapter:
        return SubprocessAdapter(self.adapter_id, prepared.python, ADAPTER_SCRIPT, trial_tag)

    def build_spec(self, prepared: PreparedFixture) -> dict[str, object]:
        return {
            "accepted_server": {"command": str(prepared.python), "args": [str(LIBRARY_SERVER)]},
            "rejected_server": {"command": str(prepared.python), "args": [str(WEB_SERVER)]},
        }

    def residual_filter(self, resource: Resource) -> bool:
        return resource.detail.get("SHUTDOWN_INTEGRITY_ROLE") == "rejected"

    def repro_command(self, prepared: PreparedFixture) -> str:
        """A literal, copy-pasteable command. Backgrounds the adapter with its
        stdin held open for 5s after the request (plain `<<<` closes stdin the
        instant the request is sent, which ends the adapter's read loop and
        lets it exit before a human has time to inspect anything), then greps
        for the rejected-role residual while that window is still open.
        Verified by hand against main-unpatched: the grep hits at t+1.5s.
        """
        spec = self.build_spec(prepared)
        request = shlex.quote(json.dumps({"op": "start_session", "spec": spec}))
        repro_python = Path(prepared.python).relative_to(REPO_ROOT)
        repro_adapter = ADAPTER_SCRIPT.relative_to(REPO_ROOT)
        launch = shlex.quote(f"(echo {request}; sleep 5) | {repro_python} {repro_adapter}")
        return (
            f"SHUTDOWN_INTEGRITY_TRIAL=demo bash -c {launch} & sleep 1.5; "
            f"ps -eo pid,ppid,cmd --no-headers | grep web_server.py | grep -v grep; wait"
        )


REJECTED_CONNECT_HARNESS = RejectedConnectHarness()
