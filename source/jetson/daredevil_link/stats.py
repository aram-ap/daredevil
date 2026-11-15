"""Link health from ACKs: round-trip time, lost and rejected commands.

Every command the Jetson sends carries a seq; the bracelet's ACK echoes it.
Record each send with sent(), pass every received frame to received(), and
call expire() now and then so unanswered commands are counted as lost.
Times are plain seconds (e.g. time.monotonic()), passed in so tests need no clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from . import protocol as p

# A command with no ACK after this long counts as lost (the bracelet's own
# watchdog window is 0.5 s too).
DEFAULT_TIMEOUT_S = 0.5


@dataclass(frozen=True)
class LinkStats:
    sent: int
    acked: int
    lost: int
    rejected: int  # ACKed, but with a status other than OK
    rtt_min: Optional[float]
    rtt_avg: Optional[float]
    rtt_max: Optional[float]

    def __str__(self) -> str:
        line = f"sent {self.sent}, acked {self.acked}, lost {self.lost}, rejected {self.rejected}"
        if self.rtt_avg is not None:
            line += (
                f"; round trip min {self.rtt_min * 1000:.1f} ms,"
                f" avg {self.rtt_avg * 1000:.1f} ms, max {self.rtt_max * 1000:.1f} ms"
            )
        return line


class AckTracker:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT_S) -> None:
        self.timeout = timeout
        self._pending: Dict[int, float] = {}  # seq -> time sent
        self._sent = 0
        self._acked = 0
        self._lost = 0
        self._rejected = 0
        self._rtts: List[float] = []

    def sent(self, seq: int, now: float) -> None:
        if seq in self._pending:
            # seq wrapped around while the old command was still unanswered.
            self._lost += 1
        self._pending[seq] = now
        self._sent += 1

    def received(self, frame: p.Frame, now: float) -> Optional[float]:
        """Return the round-trip time if this frame ACKs a pending command, else None."""
        if frame.type != p.MSG_ACK or frame.seq not in self._pending:
            return None
        rtt = now - self._pending.pop(frame.seq)
        self._acked += 1
        self._rtts.append(rtt)
        if len(frame.payload) >= 2 and frame.payload[1] != p.STATUS_OK:
            self._rejected += 1
        return rtt

    def expire(self, now: float) -> None:
        """Count commands that have waited longer than the timeout as lost."""
        late = [seq for seq, t in self._pending.items() if now - t > self.timeout]
        for seq in late:
            del self._pending[seq]
        self._lost += len(late)

    def stats(self) -> LinkStats:
        rtts = self._rtts
        return LinkStats(
            sent=self._sent,
            acked=self._acked,
            lost=self._lost,
            rejected=self._rejected,
            rtt_min=min(rtts) if rtts else None,
            rtt_avg=sum(rtts) / len(rtts) if rtts else None,
            rtt_max=max(rtts) if rtts else None,
        )
