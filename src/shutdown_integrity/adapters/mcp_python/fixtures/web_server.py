"""Stdio MCP server fixture: derived from docs_src/session_groups/tutorial002.py
in suts/mcp-python-sdk. See library_server.py for why the tool name collides.
"""

from mcp.server import MCPServer

mcp = MCPServer("Web")


@mcp.tool()
def search(query: str) -> str:
    """Search the web."""
    return f"12 pages match {query!r}."


if __name__ == "__main__":
    mcp.run()
