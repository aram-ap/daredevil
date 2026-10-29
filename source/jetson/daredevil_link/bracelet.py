"""Talk to one ESP32 bracelet over USB serial."""

from __future__ import annotations

import glob
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import serial  # pyserial

from . import protocol as p

# The XIAO ESP32-C3 uses the chip's native USB, so it enumerates as ttyACM*.
DEFAULT_PORT_GLOB = "/dev/ttyACM*"
# Time for the board to finish booting if opening the port reset it.
BOOT_DELAY_S = 1.0


@dataclass(frozen=True)
class Identity:
    side: int
    fw_version: str
    num_motors: int

    @property
    def side_name(self) -> str:
        return {p.SIDE_LEFT: "left", p.SIDE_RIGHT: "right"}.get(self.side, "unknown")


class Bracelet:
    def __init__(self, port: str, boot_delay: float = BOOT_DELAY_S) -> None:
        self.port = port
        self.identity: Optional[Identity] = None
        self._seq = 0
        self._parser = p.FrameParser()

        # Native-USB ESP32s can reset when DTR/RTS toggle on open, so hold both
        # low before opening. Baud rate is ignored by USB CDC but pyserial needs one.
        self._ser = serial.Serial()
        self._ser.port = port
        self._ser.baudrate = 115200
        self._ser.timeout = 0
        self._ser.dtr = False
        self._ser.rts = False
        self._ser.open()
        time.sleep(boot_delay)
        self._ser.reset_input_buffer()

    def __enter__(self) -> "Bracelet":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._ser.is_open:
            try:
                self.set_motors([0] * p.NUM_MOTORS)
            finally:
                self._ser.close()

    def send(self, msg_type: int, payload: bytes = b"") -> int:
        """Send one frame and return the seq number it was sent with."""
        seq = self._seq
        self._seq = (self._seq + 1) & 0xFF
        self._ser.write(p.encode_frame(msg_type, seq, payload))
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
        waiting = self._ser.in_waiting
        if not waiting:
            return []
        return self._parser.feed(self._ser.read(waiting))

    def identify(self, timeout: float = 1.0) -> Identity:
        self.send(p.MSG_IDENTIFY)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for frame in self.poll():
                if frame.type == p.MSG_IDENTITY and len(frame.payload) >= 4:
                    side, major, minor, num_motors = frame.payload[:4]
                    self.identity = Identity(side, f"{major}.{minor}", num_motors)
                    return self.identity
            time.sleep(0.01)
        raise TimeoutError(f"no IDENTITY reply from {self.port}")


def find_bracelets(port_glob: str = DEFAULT_PORT_GLOB) -> Dict[str, Bracelet]:
    """Open every matching port, ask it to identify, and key the results by side.

    Ports that don't answer are closed and skipped.
    """
    found: Dict[str, Bracelet] = {}
    for port in sorted(glob.glob(port_glob)):
        try:
            bracelet = Bracelet(port)
        except serial.SerialException:
            continue
        try:
            identity = bracelet.identify()
        except TimeoutError:
            bracelet.close()
            continue
        found[identity.side_name] = bracelet
    return found
