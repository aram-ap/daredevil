"""Talk to one ESP32 bracelet over any transport (USB serial, UDP, ...)."""

from __future__ import annotations

import glob
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from . import protocol as p
from .transport import SerialTransport, Transport

# The XIAO ESP32-C3 uses the chip's native USB, so it enumerates as ttyACM*.
DEFAULT_PORT_GLOB = "/dev/ttyACM*"


@dataclass(frozen=True)
class Identity:
    side: int
    fw_version: str
    num_motors: int

    @classmethod
    def from_payload(cls, payload: bytes) -> "Identity":
        side, major, minor, num_motors = payload[:4]
        return cls(side, f"{major}.{minor}", num_motors)

    @property
    def side_name(self) -> str:
        return {p.SIDE_LEFT: "left", p.SIDE_RIGHT: "right"}.get(self.side, "unknown")


class Bracelet:
    def __init__(self, transport: Transport, identity: Optional[Identity] = None) -> None:
        self.transport = transport
        self.identity = identity
        self._seq = 0
        self._parser = p.FrameParser()
        self._closed = False

    def __enter__(self) -> "Bracelet":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.set_motors([0] * p.NUM_MOTORS)
        finally:
            self.transport.close()

    def send(self, msg_type: int, payload: bytes = b"") -> int:
        """Send one frame and return the seq number it was sent with."""
        seq = self._seq
        self._seq = (self._seq + 1) & 0xFF
        self.transport.write(p.encode_frame(msg_type, seq, payload))
        return seq

    def set_motors(self, intensities: Sequence[int]) -> int:
        if len(intensities) != p.NUM_MOTORS:
            raise ValueError(f"expected {p.NUM_MOTORS} intensities, got {len(intensities)}")
        if any(not 0 <= v <= 255 for v in intensities):
            raise ValueError("intensities must be in 0..255")
        return self.send(p.MSG_SET_MOTORS, bytes(intensities))

    def heartbeat(self) -> int:
        return self.send(p.MSG_HEARTBEAT)

    def poll(self) -> List[p.Frame]:
        """Return any frames received so far, without blocking.

        Call this regularly: the bracelet ACKs every command, and an undrained
        input buffer would eventually stall it.
        """
        data = self.transport.read()
        return self._parser.feed(data) if data else []

    def identify(self, timeout: float = 1.0) -> Identity:
        self.send(p.MSG_IDENTIFY)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for frame in self.poll():
                if frame.type == p.MSG_IDENTITY and len(frame.payload) >= 4:
                    self.identity = Identity.from_payload(frame.payload)
                    return self.identity
            time.sleep(0.01)
        raise TimeoutError(f"no IDENTITY reply over {self.transport!r}")


def find_bracelets(port_glob: str = DEFAULT_PORT_GLOB) -> Dict[str, Bracelet]:
    """Open every matching USB serial port, ask it to identify, key results by side.

    Ports that don't answer are closed and skipped.
    """
    found: Dict[str, Bracelet] = {}
    for port in sorted(glob.glob(port_glob)):
        try:
            bracelet = Bracelet(SerialTransport(port))
        except OSError:  # serial.SerialException is an OSError
            continue
        try:
            identity = bracelet.identify()
        except TimeoutError:
            bracelet.close()
            continue
        found[identity.side_name] = bracelet
    return found
