"""Stdio MCP server fixture: derived from docs_src/session_groups/tutorial001.py
in suts/mcp-python-sdk, the SDK's own documented multi-server example. Exposes
a tool named "search", deliberately colliding with web_server.py's tool of the
same name, which is what triggers issue 3490's duplicate-name rejection path.

Run standalone with the fixture's own venv interpreter, never imported.
"""

from mcp.server import MCPServer

mcp = MCPServer("Library")


@mcp.tool()
def search(query: str) -> str:
    """Search the library catalog."""
    return f"3 books match {query!r}."


if __name__ == "__main__":
    mcp.run()
