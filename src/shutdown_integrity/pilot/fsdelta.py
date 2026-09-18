"""Filesystem delta probe: what files an episode's working directory gained.

Deliberately narrow, matching PILOT_BRIEF.md's scope limit: a size-and-mtime
snapshot of one directory tree, diffed before and after. No content hashing,
no attribution beyond "under this episode's workdir", no coverage of files
written outside it. That gap belongs in the write-up, not hidden by a probe
that quietly tries to do more than it can attribute correctly.
"""

from dataclasses import dataclass
from pathlib import Path

FileSnapshot = dict[str, tuple[int, int]]  # relpath -> (size, mtime_ns)


def snapshot_dir(root: Path) -> FileSnapshot:
    """Every regular file under root, keyed by path relative to root.

    Missing root (not yet created) snapshots as empty, not an error: the
    "before" snapshot of a fresh episode workdir is legitimately empty.
    """
    if not root.exists():
        return {}
    snapshot: FileSnapshot = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        stat = path.stat()
        snapshot[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


@dataclass(frozen=True)
class FsDelta:
    created: tuple[str, ...]
    modified: tuple[str, ...]
    removed: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.created or self.modified or self.removed)


def diff_snapshots(before: FileSnapshot, after: FileSnapshot) -> FsDelta:
    created = tuple(sorted(set(after) - set(before)))
    removed = tuple(sorted(set(before) - set(after)))
    modified = tuple(sorted(path for path in set(before) & set(after) if before[path] != after[path]))
    return FsDelta(created=created, modified=modified, removed=removed)
