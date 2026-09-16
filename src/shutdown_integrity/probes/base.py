"""Resource probes.

Attribution is by inherited environment tag, never by PID ancestry. An orphaned
grandchild is reparented to PID 1 the moment its parent dies, which destroys
ancestry in exactly the case this benchmark exists to detect. Environment is
inherited down the whole tree and survives reparenting, so it still identifies
the trial that spawned the process. PID ancestry is a cross-check only.
"""

from dataclasses import dataclass, field
from typing import Protocol

TRIAL_TAG_ENV = "SHUTDOWN_INTEGRITY_TRIAL"


@dataclass(frozen=True)
class Resource:
    """One observed resource. `identity` is unique within `kind`."""

    kind: str
    identity: str
    detail: dict[str, str] = field(default_factory=dict)


class Probe(Protocol):
    """Enumerates resources currently attributable to a trial.

    Probes answer structural questions ("does X still exist"). Behavioural
    isolation questions ("can session B observe session A's state") do not fit
    this shape and are driven through the adapter instead. See DESIGN.md, open
    question 1.
    """

    kind: str

    def snapshot(self, trial_tag: str) -> tuple[Resource, ...]: ...
