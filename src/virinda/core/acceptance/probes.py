from __future__ import annotations

import os
import resource
import threading
from pathlib import Path
from time import monotonic_ns

from virinda.core.acceptance.models import LEGAL_TRANSITIONS, ResourceSnapshot, TurnState


class ResourceProbe:
    """Collects precise process resource metrics (RSS, FDs, thread count)."""

    @staticmethod
    def sample() -> ResourceSnapshot:
        rss = 0
        vms = 0
        try:
            # On Linux, resource.getrusage(RUSAGE_SELF).ru_maxrss is in kilobytes
            usage = resource.getrusage(resource.RUSAGE_SELF)
            rss = usage.ru_maxrss * 1024
        except Exception:
            pass

        # Try reading exact /proc/self/statm on Linux if available
        try:
            statm = Path("/proc/self/statm").read_text().split()
            if statm:
                page_size = os.sysconf("SC_PAGE_SIZE")
                vms = int(statm[0]) * page_size
                rss = int(statm[1]) * page_size
        except Exception:
            pass

        # Count open file descriptors on Linux
        fd_count = 0
        try:
            fd_dir = Path("/proc/self/fd")
            if fd_dir.exists():
                fd_count = len(list(fd_dir.iterdir()))
        except Exception:
            pass

        threads = threading.enumerate()
        thread_names = tuple(sorted(t.name for t in threads))

        return ResourceSnapshot(
            timestamp_ns=monotonic_ns(),
            rss_bytes=rss,
            vms_bytes=vms,
            thread_count=len(threads),
            fd_count=fd_count,
            thread_names=thread_names,
        )


class MessageBusProbe:
    """Observes message bus state transitions and validates lifecycle legality."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []
        self.states: list[TurnState] = []
        self.illegal_transitions: list[tuple[TurnState, TurnState]] = []

    def on_state(self, new_state: TurnState) -> None:
        if self.states:
            prev_state = self.states[-1]
            allowed = LEGAL_TRANSITIONS.get(prev_state, set())
            if new_state not in allowed and new_state != prev_state:
                self.illegal_transitions.append((prev_state, new_state))
        self.states.append(new_state)

    def on_event(self, event_type: str, data: dict[str, object]) -> None:
        self.events.append({"type": event_type, "data": data, "timestamp_ns": monotonic_ns()})
        if event_type == "virinda.voice.state":
            state_str = str(data.get("state", ""))
            try:
                self.on_state(TurnState(state_str))
            except ValueError:
                pass
