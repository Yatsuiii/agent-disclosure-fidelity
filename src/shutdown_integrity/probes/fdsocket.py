"""File descriptor and socket probe.

Socket state matters as much as socket count. A connection parked in CLOSE_WAIT
is the signature of a peer that closed while the local side never called close,
which is the accumulation failure reported in mcp python-sdk issue 2958. A
count-only probe would report that socket as healthy.
"""

from shutdown_integrity.probes.base import Resource


class FdSocketProbe:
    kind = "fd"

    def snapshot(self, trial_tag: str) -> tuple[Resource, ...]:
        """Open descriptors held by processes carrying the trial tag.

        detail should carry at least: fd type (socket, pipe, file), and for
        sockets the TCP state and peer address.
        """
        raise NotImplementedError
