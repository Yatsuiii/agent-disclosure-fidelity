// Adapter subprocess for the smithery-cli discovery finding
// (uplink.ts's createStdioLocalPeer: hand-rolled spawn/close, no
// process-group awareness, no stated contract; see DISCOVERY.md).
//
// Drives the SUT's real, exported, shipped entry point (`serveUplink`),
// never a reimplementation: createStdioLocalPeer itself is module-private,
// so this is the only way to exercise shipped code rather than a copy of
// it, which is what closes the "a maintainer could say surrounding code
// handles it" gap DISCOVERY.md's smithery-cli row flagged as open.
//
// serveUplink() needs a paired WebSocket to Smithery's cloud uplink relay
// before it will run at all. This adapter starts an in-process mock of
// that relay (mockRelay.mjs) and points serveUplink at it via
// SMITHERY_UPLINK_BASE_URL, a real override the SUT's own code already
// supports (uplink.ts:673, read directly from source, not invented).
// The mock only needs to accept the WebSocket upgrade: serveUplink's own
// code path calls `await local.start()` (spawn the real child, run a real
// MCP initialize handshake against it) BEFORE it ever pairs the socket, so
// by the time our mock sees a connection, the shipped local-spawn code has
// already fully run (uplink.ts:308-312, read directly, confirms the order).
//
// Runs under `tsx` so it can import suts/smithery-cli/src/lib/uplink.ts
// (a .ts file) directly, matching how the SUT's own test suite imports it
// (src/lib/__tests__/uplink.test.ts) rather than needing a build step this
// benchmark would have to maintain.
//
// __SMITHERY_VERSION__ is an esbuild `--define` in the SUT's real build
// (build.mjs:69); tsx does not run that build, so it is polyfilled the same
// way the SUT's own test suite polyfills it
// (src/lib/__tests__/uplink.test.ts:17: `globalThis.__SMITHERY_VERSION__ =
// globalThis.__SMITHERY_VERSION__ ?? "test"`), not invented for this adapter.
//
// Teardown is delivered as a real SIGTERM to this process. serveUplink()
// registers `process.on("SIGTERM", handleSignal)` itself (uplink.ts:196),
// which is exactly how a real user's Ctrl-C or a process manager's
// shutdown signal reaches it, so this is the most faithful way to trigger
// its close() path, not a proxy for it.

import readline from 'node:readline';
import { startMockRelay } from './fixtures/mockRelay.mjs';

globalThis.__SMITHERY_VERSION__ = globalThis.__SMITHERY_VERSION__ ?? 'test';

// serveUplink() writes user-facing CLI progress via console.log (e.g.
// "Pairing uplink ... connected"), which shares stdout with this adapter's
// NDJSON wire protocol. console.error already goes to stderr by default and
// is left alone; only console.log needs redirecting so stdout stays exactly
// one JSON object per line.
console.log = (...args) => console.error(...args);

const sutRoot = process.env.SHUTDOWN_INTEGRITY_SUT_ROOT;
if (!sutRoot) {
    throw new Error('SHUTDOWN_INTEGRITY_SUT_ROOT must be set');
}

const { serveUplink } = await import(`${sutRoot}/src/lib/uplink.ts`);

let session = null;

async function opStartSession(req) {
    const spec = req.spec;
    const relay = await startMockRelay(sutRoot);
    process.env.SMITHERY_API_KEY = 'shutdown-integrity-fake-key';
    process.env.SMITHERY_UPLINK_BASE_URL = relay.baseUrl;

    const pairedPromise = relay.waitForConnection();

    const donePromise = serveUplink({
        namespace: 'shutdown-integrity',
        connectionId: `trial-${Date.now()}`,
        target: {
            kind: 'uplink-stdio',
            command: spec.command,
            args: spec.args,
            env: spec.env,
        },
    });

    // Resolves only once serveUplink has paired the socket, which per
    // uplink.ts's own connect() only happens after `await local.start()`
    // has already fully run (see module docstring). This is the real
    // synchronization point the SUT's own code provides, not a poll loop.
    await pairedPromise;

    const handle = 'smithery-session';
    session = { donePromise, relay };
    return { ok: true, handle };
}

async function opExercise(req) {
    if (session === null) {
        return { ok: false, error: 'no active session' };
    }
    // wrapInitialized's real initialize + notifications/initialized
    // handshake already ran as part of local.start() before start_session
    // returned (uplink.ts:456-479): that is the live-session proof: a
    // second, separate tool call is not meaningful here since this
    // scenario is about close(), not the MCP protocol surface.
    return { ok: true, result: 'initialize handshake already completed during start_session' };
}

async function opTeardown() {
    if (session === null) {
        return { ok: false, error: 'no active session' };
    }
    const { donePromise, relay } = session;
    session = null;

    const t0 = process.hrtime.bigint();
    process.kill(process.pid, 'SIGTERM');
    await donePromise;
    const returnedAfterS = Number(process.hrtime.bigint() - t0) / 1e9;

    await relay.close();
    return { ok: true, returned_after_s: returnedAfterS };
}

async function dispatch(req) {
    switch (req.op) {
        case 'declare_capabilities':
            return { ok: true, capabilities: ['stdio'] };
        case 'start_session':
            return opStartSession(req);
        case 'exercise':
            return opExercise(req);
        case 'teardown':
            return opTeardown();
        default:
            return { ok: false, error: `unsupported op for this adapter: ${req.op}` };
    }
}

const rl = readline.createInterface({ input: process.stdin, terminal: false });
rl.on('line', line => {
    const trimmed = line.trim();
    if (!trimmed) {
        return;
    }
    (async () => {
        let reply;
        try {
            reply = await dispatch(JSON.parse(trimmed));
        } catch (err) {
            reply = { ok: false, error: `${err.name}: ${err.message}` };
        }
        process.stdout.write(`${JSON.stringify(reply)}\n`);
    })();
});
