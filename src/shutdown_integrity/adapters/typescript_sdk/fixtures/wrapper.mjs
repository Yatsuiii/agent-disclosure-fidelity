// Minimal stand-in for a real-world wrapper (npx, uvx, python -m): a program
// that spawns the actual MCP server as a child with inherited stdio and
// stays alive until the child exits. This is deliberately NOT a shell
// backgrounding trick (`sh -c 'cmd & wait'`) — POSIX shells redirect a
// backgrounded async command's stdin to /dev/null when job control is off
// (verified: `echo x | sh -c 'cat & wait $!'` prints nothing), which breaks
// the JSON-RPC stdio the MCP server actually needs. Real wrappers spawn a
// child with genuine fd inheritance instead, which is what this does.
//
// Node's default disposition does NOT propagate a parent's death or a
// SIGTERM to its children, so killing this wrapper process alone (the
// unpatched typescript-sdk#2023 behavior) leaves the grandchild it spawned
// running, exactly like the real npx/uvx case the issue describes.

import { spawn } from 'node:child_process';

const [, , command, ...args] = process.argv;

const child = spawn(command, args, { stdio: 'inherit' });
child.on('exit', code => process.exit(code ?? 0));
