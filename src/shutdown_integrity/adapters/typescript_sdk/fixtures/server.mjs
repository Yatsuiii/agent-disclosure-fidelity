// Stdio MCP server fixture: derived from README.md's own "Getting Started"
// example in suts/typescript-sdk (McpServer + StdioServerTransport, a single
// registered tool). inputSchema is omitted (it is optional per
// packages/server/src/server/mcp.ts's ToolConfig) rather than pulled in via
// zod, since zod is not resolvable by bare specifier from outside the SUT's
// own package tree and this scenario needs no argument validation: exercise()
// only needs to prove the session is genuinely live, not exercise validation.
//
// Run standalone with `node server.mjs`, never imported. SUT_ROOT is passed
// as argv[2] so this fixture has no hardcoded path back into the repo.
//
// Keeps a plain setInterval alive (not .unref()'d) so the process does not
// exit merely because its stdin reaches EOF. Verified directly: an MCP
// server built only from McpServer + StdioServerTransport, with nothing else
// referencing the event loop, exits on its own the instant stdin closes,
// with no signal involved at all (`node server.mjs < /dev/null` exits
// immediately). That would make every trial "pass" regardless of whether
// close() reaches the whole process tree, since EOF alone (propagated
// through the wrapper's inherited stdio) would clean everything up before a
// kill signal ever mattered. The interval stands in for the background work
// (an open upstream connection, a health-check loop) that real wrapped MCP
// servers commonly have and that is exactly why issue #2023's orphans don't
// clean themselves up.

const sutRoot = process.argv[2];
if (!sutRoot) {
    throw new Error('usage: node server.mjs <path-to-suts/typescript-sdk>');
}

const { McpServer } = await import(`${sutRoot}/packages/server/dist/index.mjs`);
const { StdioServerTransport } = await import(`${sutRoot}/packages/server/dist/stdio.mjs`);

const server = new McpServer({ name: 'shutdown-integrity-fixture-server', version: '1.0.0' });

server.registerTool(
    'ping',
    { description: 'Return a fixed reply, to prove the session is live.' },
    async () => ({ content: [{ type: 'text', text: 'pong' }] })
);

setInterval(() => {}, 60_000);

const transport = new StdioServerTransport();
await server.connect(transport);
