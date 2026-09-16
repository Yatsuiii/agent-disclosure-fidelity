"""Process probe: every live process carrying the trial's environment tag.

Must walk descendants, not just direct children. The wrapper case (npx, uvx,
python -m, sh -c) is where the real bug lives: killing the direct child leaves
the actual server running as a grandchild.

Reads /proc directly rather than through psutil. Attribution needs exactly two
things psutil would only wrap: a process's environ (to read the trial tag) and
its cmdline. Linux-only by construction, which matches the rest of this
benchmark for v1 (see DESIGN.md, v1 scope).
"""

from pathlib import Path

from shutdown_integrity.probes.base import Resource

TRIAL_TAG_ENV = "SHUTDOWN_INTEGRITY_TRIAL"
_DETAIL_ENV_PREFIX = "SHUTDOWN_INTEGRITY_"

_PROC = Path("/proc")


def _read_environ(pid: str) -> dict[str, str] | None:
    """Parses /proc/<pid>/environ. None if the process is gone or unreadable.

    A process that exits between listing /proc and this read is not a leak,
    it is a race with the observer, so callers must treat None as "skip", not
    as "found nothing".
    """
    try:
        raw = (_PROC / pid / "environ").read_bytes()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None
    entries = raw.split(b"\0")
    env: dict[str, str] = {}
    for entry in entries:
        if not entry:
            continue
        key, sep, value = entry.partition(b"=")
        if not sep:
            continue
        env[key.decode("utf-8", "surrogateescape")] = value.decode("utf-8", "surrogateescape")
    return env


def _read_cmdline(pid: str) -> str:
    try:
        raw = (_PROC / pid / "cmdline").read_bytes()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return ""
    parts = [p.decode("utf-8", "surrogateescape") for p in raw.split(b"\0") if p]
    return " ".join(parts)


def _read_stat_field(pid: str, field_index: int) -> str:
    """field_index is 0-based over the whitespace-split fields after the
    parenthesised comm, so ppid is index 1 and starttime is index 19 per
    proc(5). The comm field itself can contain spaces or parens, hence the
    rsplit on ')' rather than a naive split.
    """
    try:
        raw = (_PROC / pid / "stat").read_text(encoding="utf-8")
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return ""
    _, _, rest = raw.rpartition(")")
    fields = rest.split()
    if field_index >= len(fields):
        return ""
    return fields[field_index]


class ProcessTreeProbe:
    kind = "process"

    def snapshot(self, trial_tag: str) -> tuple[Resource, ...]:
        """Live processes whose environ carries SHUTDOWN_INTEGRITY_TRIAL=trial_tag.

        Walking all of /proc rather than descending from a known root is
        deliberate: an orphaned grandchild is reparented to PID 1 the instant
        its parent dies, so ancestry cannot be relied on to reach it. A full
        scan finds it anyway because the tag survives reparenting. detail
        also surfaces every other SHUTDOWN_INTEGRITY_* env var verbatim
        (e.g. a per-connection role tag), so scenario-specific verdict logic
        can filter without this probe needing scenario-specific knowledge.
        """
        resources: list[Resource] = []
        for entry in _PROC.iterdir():
            pid = entry.name
            if not pid.isdigit():
                continue
            env = _read_environ(pid)
            if env is None or env.get(TRIAL_TAG_ENV) != trial_tag:
                continue
            detail = {
                "pid": pid,
                "ppid": _read_stat_field(pid, 1),
                "cmdline": _read_cmdline(pid),
                "create_time": _read_stat_field(pid, 19),
            }
            for key, value in env.items():
                if key.startswith(_DETAIL_ENV_PREFIX) and key != TRIAL_TAG_ENV:
                    detail[key] = value
            resources.append(Resource(kind=self.kind, identity=pid, detail=detail))
        return tuple(resources)
