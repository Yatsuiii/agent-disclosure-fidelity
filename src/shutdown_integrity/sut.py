"""Prepares an isolated SUT build for one control fixture, per ecosystem.

A scenario's arming gate needs two SUT builds that differ by exactly one
patch: the broken control and the fixed control. Each pinned checkout under
suts/ stays untouched (HANDOFF.md forbids editing it); the fixed control is
produced in a separate git worktree with the patch applied there instead, so
the two builds never share mutable state and the pinned checkout stays a
trustworthy reference for every future session. That worktree-plus-patch
step is identical across ecosystems and lives in `_prepare_worktree`.

What differs is how a checkout becomes runnable. Python isolates a patched
and an unpatched `mcp` package by giving each fixture its own venv
(`prepare`). The TypeScript SDK isolates them by directory instead: each
fixture's worktree gets its own `pnpm install` + build, and the adapter
imports the built output by absolute path rather than through node_modules
resolution, so no per-fixture "interpreter" concept is needed at all
(`prepare_node`). Forcing both through one PreparedFixture shape would give
the Node case a `python` field that means nothing; they return distinct types
instead.
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from shutdown_integrity.scenario import ControlFixture

REPO_ROOT = Path(__file__).resolve().parents[2]
SUT_CHECKOUT = REPO_ROOT / "suts" / "mcp-python-sdk"
TS_SUT_CHECKOUT = REPO_ROOT / "suts" / "typescript-sdk"
SMITHERY_CLI_SUT_CHECKOUT = REPO_ROOT / "suts" / "smithery-cli"
WORKTREES_DIR = REPO_ROOT / ".worktrees"
VENVS_DIR = REPO_ROOT / ".venvs"
UV_CACHE_DIR = REPO_ROOT / ".uv-cache"
NPM_CACHE_DIR = REPO_ROOT / ".npm-cache"
PNPM_STORE_DIR = REPO_ROOT / ".pnpm-store"
PNPM_VERSION = "10.26.1"  # must match typescript-sdk's own package.json#packageManager
SMITHERY_CLI_PNPM_VERSION = "10.27.0"  # must match smithery-cli's own package.json#packageManager

# Building only these two workspace packages (plus their deps) is enough:
# tsdown bundles @modelcontextprotocol/core-internal straight into each
# package's own dist output (see packages/client/tsdown.config.ts's
# `noExternal`), and @modelcontextprotocol/server never needs a per-fixture
# build at all, since PR #2024 touches only packages/client/src/client/stdio.ts
# (see adapters/typescript_sdk/harness.py for why the fixture server always
# imports from the stable checkout instead).
_TS_PNPM_FILTERS = ("@modelcontextprotocol/client...", "@modelcontextprotocol/core...")
_TS_BUILD_TARGETS = ("@modelcontextprotocol/core", "@modelcontextprotocol/client")
_TS_BUILT_MARKER = Path("packages") / "client" / "dist" / "stdio.mjs"


def _uv_env() -> dict[str, str]:
    """Pins uv's cache to the Windows mount. Root filesystem has ~6G free
    (HANDOFF.md); an uncontained uv cache can exhaust it.
    """
    env = dict(os.environ)
    env["UV_CACHE_DIR"] = str(UV_CACHE_DIR)
    return env


def _npm_env() -> dict[str, str]:
    """Pins npm/pnpm's own package cache to the Windows mount, same reasoning
    as _uv_env. pnpm's content-addressed store is pinned separately via
    --store-dir on each invocation, not through this env.
    """
    env = dict(os.environ)
    env["npm_config_cache"] = str(NPM_CACHE_DIR)
    return env


@dataclass(frozen=True)
class PreparedFixture:
    """A Python fixture ready to run: an interpreter with the SUT installed."""

    name: str
    source_dir: Path
    python: Path


@dataclass(frozen=True)
class PreparedNodeFixture:
    """A TypeScript fixture ready to run: a built checkout to import from.

    There is no per-fixture executable: the adapter always runs under the
    system `node` and imports this SUT build by absolute path.
    """

    name: str
    source_dir: Path


def _run(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True, capture_output=True, text=True)


def _prepare_worktree(fixture: ControlFixture, sut_checkout: Path, worktrees_dir: Path) -> Path:
    """Returns a source directory checked out at fixture.sut_ref with fixture.patch
    applied, reusing an existing worktree if one is already in the right state.
    """
    if fixture.patch is None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=sut_checkout, check=True, capture_output=True, text=True
        ).stdout.strip()
        if head != fixture.sut_ref:
            raise RuntimeError(
                f"{sut_checkout} is at {head}, expected pinned commit {fixture.sut_ref}. "
                "Reclone or update the pin before running this fixture."
            )
        return sut_checkout

    worktree_dir = worktrees_dir / fixture.name
    patch_path = REPO_ROOT / fixture.patch
    if worktree_dir.exists():
        result = subprocess.run(["git", "-C", str(worktree_dir), "diff", "--quiet"], capture_output=True)
        if result.returncode == 0:
            # Clean tree where a patch should be applied: either never applied
            # or reset out from under us. Either way, re-apply from scratch.
            subprocess.run(["git", "apply", str(patch_path)], cwd=worktree_dir, check=True, capture_output=True)
        return worktree_dir

    worktrees_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree_dir), fixture.sut_ref],
        cwd=sut_checkout,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "apply", str(patch_path)], cwd=worktree_dir, check=True, capture_output=True, text=True)
    return worktree_dir


def prepare(fixture: ControlFixture) -> PreparedFixture:
    """Idempotent: safe to call once per fixture per process, reuses an
    existing venv and worktree if already built in the right state.
    """
    source_dir = _prepare_worktree(fixture, SUT_CHECKOUT, WORKTREES_DIR)
    venv_dir = VENVS_DIR / fixture.name
    python = venv_dir / "bin" / "python"

    if not python.exists():
        VENVS_DIR.mkdir(parents=True, exist_ok=True)
        _run(["uv", "venv", str(venv_dir)], env=_uv_env())
        _run(["uv", "pip", "install", "--python", str(python), "-e", str(source_dir)], env=_uv_env())

    return PreparedFixture(name=fixture.name, source_dir=source_dir, python=python)


def _pnpm(args: list[str], cwd: Path, pnpm_version: str = PNPM_VERSION) -> None:
    _run(
        ["npx", "--yes", f"pnpm@{pnpm_version}", *args, "--store-dir", str(PNPM_STORE_DIR)],
        cwd=cwd,
        env=_npm_env(),
    )


def prepare_node(fixture: ControlFixture) -> PreparedNodeFixture:
    """Idempotent, same contract as prepare(). Each fixture's worktree gets
    its own `pnpm install` and build: the worktree is a full copy of the
    monorepo, so pnpm's own content-addressed store (shared via --store-dir)
    makes a second fixture's install fast even though it is a separate tree.

    Installs with --ignore-scripts and separately rebuilds only esbuild's own
    postinstall. The monorepo root's own `prepare` script runs `lefthook
    install`, which refuses to run (correctly) because this machine's global
    `core.hooksPath` is already set elsewhere for an unrelated project-wide
    hook; forcing it would overwrite that global hook, so it must never run
    at all here, not merely be tolerated.
    """
    source_dir = _prepare_worktree(fixture, TS_SUT_CHECKOUT, WORKTREES_DIR)
    if not (source_dir / _TS_BUILT_MARKER).exists():
        _pnpm(
            ["install", "--frozen-lockfile", "--ignore-scripts", *(f"--filter={f}" for f in _TS_PNPM_FILTERS)],
            cwd=source_dir,
        )
        _pnpm(["rebuild", "esbuild"], cwd=source_dir)
        for target in _TS_BUILD_TARGETS:
            _pnpm(["--filter", target, "build"], cwd=source_dir)

    return PreparedNodeFixture(name=fixture.name, source_dir=source_dir)


_SMITHERY_CLI_BUILT_MARKER = Path("node_modules") / ".bin" / "tsx"


def prepare_smithery_cli(fixture: ControlFixture) -> PreparedNodeFixture:
    """Idempotent, same contract as prepare()/prepare_node(). A single-package
    pnpm project, unlike the TS SDK's workspace: `pnpm install` alone is
    enough, no build step, since the adapter runs the SUT's own TypeScript
    source directly via `tsx` (matching how the SUT's own test suite imports
    it, e.g. src/lib/__tests__/uplink.test.ts) rather than importing a built
    bundle. Reuses PreparedNodeFixture: there is equally no per-fixture
    executable here, `tsx` resolves from the prepared source_dir's own
    node_modules regardless of which fixture is active.
    """
    source_dir = _prepare_worktree(fixture, SMITHERY_CLI_SUT_CHECKOUT, WORKTREES_DIR)
    if not (source_dir / _SMITHERY_CLI_BUILT_MARKER).exists():
        _pnpm(
            ["install", "--frozen-lockfile", "--ignore-scripts"],
            cwd=source_dir,
            pnpm_version=SMITHERY_CLI_PNPM_VERSION,
        )
    return PreparedNodeFixture(name=fixture.name, source_dir=source_dir)
