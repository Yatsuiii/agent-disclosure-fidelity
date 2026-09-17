// Adapter subprocess for typescript-sdk#2023
// (StdioClientTransport.close() does not kill the process tree).
//
// Speaks the same NDJSON wire protocol documented in
// shutdown_integrity/adapter.py, over stdin/stdout, one persistent process
// for its whole lifetime (mirrors adapter_main.py's reasoning: the Client and
// its transport are stateful objects that must survive across separate
// start_session / exercise / teardown calls).
//
// Derived from suts/typescript-sdk's own documented usage
// (docs/get-started/first-client.md: Client + StdioClientTransport, connect,
// callTool, close), the exact call sequence issue #2023 sits in.
//
// The SUT root (a path to a typescript-sdk checkout or worktree with
// packages/client already built) is read from SHUTDOWN_INTEGRITY_SUT_ROOT
// rather than argv, so the launcher (SubprocessAdapter, Python side) does not
// need a TypeScript-specific constructor shape.
//
// Usage: node adapter_main.mjs, fed newline-delimited JSON on stdin.
//
// start_session spec for this scenario:
//     { "command": "sh", "args": ["-c", "<node> <server.mjs> <sutRoot> & wait $!"] }
// The wrapper is the point: it makes the real MCP server a grandchild of the
// direct child StdioClientTransport spawns, which is exactly the shape
// issue #2023 describes (npx, uvx, python -m all have the same structure).

import readline from 'node:readline';

const sutRoot = process.env.SHUTDOWN_INTEGRITY_SUT_ROOT;
if (!sutRoot) {
    throw new Error('SHUTDOWN_INTEGRITY_SUT_ROOT must be set');
}

const { Client } = await import(`${sutRoot}/packages/client/dist/index.mjs`);
const { StdioClientTransport } = await import(`${sutRoot}/packages/client/dist/stdio.mjs`);

const sessions = new Map();

function serverEnv() {
    // ROLE distinguishes the spawned server-under-test from the adapter's own
    // process, which necessarily carries the trial tag too (to propagate it
    // down) but is the harness, not something under test. Without this, a
    // residual_filter that accepts every tagged process would flag the
    // adapter itself on every trial, broken or fixed alike.
    const env = { PATH: process.env.PATH ?? '', SHUTDOWN_INTEGRITY_ROLE: 'server' };
    const tag = process.env.SHUTDOWN_INTEGRITY_TRIAL;
    if (tag !== undefined) {
        env.SHUTDOWN_INTEGRITY_TRIAL = tag;
    }
    return env;
}

async function opStartSession(req) {
    const spec = req.spec;
    const handle = crypto.randomUUID();
    const transport = new StdioClientTransport({
        command: spec.command,
        args: spec.args,
        env: serverEnv()
    });
    const client = new Client({ name: 'shutdown-integrity-adapter', version: '1.0.0' });
    await client.connect(transport);
    sessions.set(handle, { client, transport });
    return { ok: true, handle };
}

async function opExercise(req) {
    const session = sessions.get(req.handle);
    const result = await session.client.callTool({ name: 'ping', arguments: {} });
    return { ok: true, result: result.content };
}

async function opTeardown(req) {
    const session = sessions.get(req.handle);
    sessions.delete(req.handle);
    const t0 = process.hrtime.bigint();
    await session.client.close();
    const returnedAfterS = Number(process.hrtime.bigint() - t0) / 1e9;
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
            return opTeardown(req);
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
