"""Byte links a Bracelet can talk over.

A transport is anything with write(bytes), read() -> bytes and close().
read() must never block: it returns whatever has arrived, possibly b"".
"""

from __future__ import annotations

import time
from typing import Protocol

# Time for the board to finish booting if opening the port reset it.
BOOT_DELAY_S = 1.0


class Transport(Protocol):
    def write(self, data: bytes) -> None: ...

    def read(self) -> bytes: ...

    def close(self) -> None: ...


class SerialTransport:
    """USB serial link to one bracelet (the XIAO shows up as /dev/ttyACM*)."""

    def __init__(self, port: str, boot_delay: float = BOOT_DELAY_S) -> None:
        import serial  # pyserial; imported here so the rest of the package works without it

        self.port = port
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

    def __repr__(self) -> str:
        return f"SerialTransport({self.port!r})"

    def write(self, data: bytes) -> None:
        self._ser.write(data)

    def read(self) -> bytes:
        waiting = self._ser.in_waiting
        return self._ser.read(waiting) if waiting else b""

    def close(self) -> None:
        self._ser.close()
