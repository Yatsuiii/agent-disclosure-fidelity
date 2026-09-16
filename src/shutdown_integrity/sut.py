"""Prepares an isolated Python environment for one control fixture.

A scenario's arming gate needs two SUT builds that differ by exactly one
patch: the broken control and the fixed control. `suts/mcp-python-sdk` stays
pinned and untouched (HANDOFF.md forbids editing it); the fixed control is
produced in a separate git worktree with the patch applied there instead, so
the two builds never share mutable state and the pinned checkout stays a
trustworthy reference for every future session.

Each fixture gets its own venv under REPO_ROOT/.venvs, installed with
`uv pip install -e`, so a patched and an unpatched `mcp` package are never
importable from the same interpreter.
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from shutdown_integrity.scenario import ControlFixture

REPO_ROOT = Path(__file__).resolve().parents[2]
SUT_CHECKOUT = REPO_ROOT / "suts" / "mcp-python-sdk"
WORKTREES_DIR = REPO_ROOT / ".worktrees"
VENVS_DIR = REPO_ROOT / ".venvs"
UV_CACHE_DIR = REPO_ROOT / ".uv-cache"


def _uv_env() -> dict[str, str]:
    """Pins uv's cache to the Windows mount. Root filesystem has ~6G free
    (HANDOFF.md); an uncontained uv cache can exhaust it.
    """
    env = dict(os.environ)
    env["UV_CACHE_DIR"] = str(UV_CACHE_DIR)
    return env


@dataclass(frozen=True)
class PreparedFixture:
    """A fixture ready to run: an interpreter with the SUT installed into it."""

    name: str
    source_dir: Path
    python: Path


def _run(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, env=_uv_env(), check=True, capture_output=True, text=True)


def _prepare_worktree(fixture: ControlFixture) -> Path:
    """Returns a source directory checked out at fixture.sut_ref with fixture.patch
    applied, reusing an existing worktree if one is already in the right state.
    """
    if fixture.patch is None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=SUT_CHECKOUT, check=True, capture_output=True, text=True
        ).stdout.strip()
        if head != fixture.sut_ref:
            raise RuntimeError(
                f"suts/mcp-python-sdk is at {head}, expected pinned commit {fixture.sut_ref}. "
                "Reclone or update the pin before running this fixture."
            )
        return SUT_CHECKOUT

    worktree_dir = WORKTREES_DIR / fixture.name
    patch_path = REPO_ROOT / fixture.patch
    if worktree_dir.exists():
        result = subprocess.run(
            ["git", "-C", str(worktree_dir), "diff", "--quiet"], capture_output=True
        )
        if result.returncode == 0:
            # Clean tree where a patch should be applied: either never applied
            # or reset out from under us. Either way, re-apply from scratch.
            subprocess.run(["git", "apply", str(patch_path)], cwd=worktree_dir, check=True, capture_output=True)
        return worktree_dir

    WORKTREES_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree_dir), fixture.sut_ref],
        cwd=SUT_CHECKOUT,
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
    source_dir = _prepare_worktree(fixture)
    venv_dir = VENVS_DIR / fixture.name
    python = venv_dir / "bin" / "python"

    if not python.exists():
        VENVS_DIR.mkdir(parents=True, exist_ok=True)
        _run(["uv", "venv", str(venv_dir)])
        _run(["uv", "pip", "install", "--python", str(python), "-e", str(source_dir)])

    return PreparedFixture(name=fixture.name, source_dir=source_dir, python=python)
