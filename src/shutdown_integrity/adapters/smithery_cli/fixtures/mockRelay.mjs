// Minimal stand-in for Smithery's cloud uplink relay (uplink.smithery.run),
// used only to get serveUplink() (suts/smithery-cli/src/lib/uplink.ts) past
// its WebSocket-pairing step. Read directly from source before writing this:
// pairUplinkSocket() (uplink.ts:324) just does `new WebSocket(url, {headers})`
// and resolves on the socket's 'open' event, nothing else. This mock accepts
// every upgrade and sends nothing, which is sufficient: no JSON-RPC frame
// ever needs to cross this socket for the spawn/initialize/close path under
// test, since local.start() (the real spawn + local MCP handshake) already
// completes before the socket even pairs (see adapter_main.mjs's docstring).
//
// Deliberately does not implement anything else of the real protocol. If a
// future scenario needs actual message relay, extend here rather than
// building a second mock.

import { createServer } from 'node:http';

export async function startMockRelay(sutRoot) {
    // `ws` lives in the SUT's own node_modules (a real runtime dependency of
    // uplink.ts, not a devDependency), resolved by absolute path since this
    // file is outside that resolution chain, same reasoning as adapter_main
    // importing serveUplink itself.
    const { WebSocketServer } = await import(`${sutRoot}/node_modules/ws/wrapper.mjs`);
    const httpServer = createServer();
    const wss = new WebSocketServer({ server: httpServer });

    let resolveConnection;
    const connectionPromise = new Promise(resolve => {
        resolveConnection = resolve;
    });
    wss.on('connection', socket => {
        resolveConnection(socket);
    });

    await new Promise(resolve => httpServer.listen(0, '127.0.0.1', resolve));
    const { port } = httpServer.address();

    return {
        baseUrl: `http://127.0.0.1:${port}`,
        waitForConnection: () => connectionPromise,
        close: () =>
            new Promise(resolve => {
                wss.close(() => httpServer.close(() => resolve()));
            }),
    };
}
