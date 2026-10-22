"""Jetson <-> ESP32 bracelet wire protocol (v1).

Every message is one binary frame:

    +------+------+------+-----+-----+-----------------+-------+
    | 0xAA | 0x55 | type | seq | len | payload (len B) | CRC-8 |
    +------+------+------+-----+-----+-----------------+-------+

- 0xAA 0x55 : sync marker, lets a receiver re-align after garbage/lost bytes
- type      : message type (MSG_* below)
- seq       : sender's rolling counter 0..255 (ACKs echo the seq they confirm)
- len       : payload length, 0..MAX_PAYLOAD
- CRC-8     : poly 0x07, init 0x00, computed over type, seq, len, payload

The same constants live in source/esp32/include/protocol.h -- keep them in sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

SYNC0 = 0xAA
SYNC1 = 0x55
HEADER_LEN = 5  # sync0, sync1, type, seq, len
MAX_PAYLOAD = 16

# Jetson -> ESP32
MSG_SET_MOTORS = 0x01  # payload: NUM_MOTORS bytes, intensity 0..255 each
MSG_HEARTBEAT = 0x02  # payload: none; keeps the link watchdog alive
MSG_IDENTIFY = 0x03  # payload: none; bracelet answers with MSG_IDENTITY

# ESP32 -> Jetson
MSG_ACK = 0x81  # seq = echoed seq; payload: [acked_type, status]
MSG_IDENTITY = 0x83  # payload: [side, fw_major, fw_minor, num_motors]

# ACK status codes
STATUS_OK = 0x00
STATUS_BAD_LENGTH = 0x01
STATUS_UNKNOWN_TYPE = 0x02

SIDE_LEFT = 0
SIDE_RIGHT = 1

NUM_MOTORS = 4


def crc8(data: bytes) -> int:
    """CRC-8 with polynomial 0x07 and initial value 0x00 (bitwise, no table)."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


@dataclass(frozen=True)
class Frame:
    type: int
    seq: int
    payload: bytes = b""


def encode_frame(msg_type: int, seq: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload too long ({len(payload)} > {MAX_PAYLOAD})")
    body = bytes([msg_type & 0xFF, seq & 0xFF, len(payload)]) + payload
    return bytes([SYNC0, SYNC1]) + body + bytes([crc8(body)])


class FrameParser:
    """Incremental decoder: feed it raw bytes as they arrive, get whole frames back.

    Bytes that don't form a valid frame (bad sync, oversized length, CRC
    mismatch) are dropped, and the parser goes back to hunting for 0xAA 0x55.
    """

    _WAIT_SYNC0, _WAIT_SYNC1, _TYPE, _SEQ, _LEN, _PAYLOAD, _CRC = range(7)

    def __init__(self) -> None:
        self.crc_errors = 0
        self._reset()

    def _reset(self) -> None:
        self._state = self._WAIT_SYNC0
        self._type = 0
        self._seq = 0
        self._len = 0
        self._payload = bytearray()

    def feed(self, data: bytes) -> List[Frame]:
        frames: List[Frame] = []
        for byte in data:
            frame = self._feed_byte(byte)
            if frame is not None:
                frames.append(frame)
        return frames

    def _feed_byte(self, byte: int):
        state = self._state
        if state == self._WAIT_SYNC0:
            if byte == SYNC0:
                self._state = self._WAIT_SYNC1
        elif state == self._WAIT_SYNC1:
            if byte == SYNC1:
                self._state = self._TYPE
            elif byte != SYNC0:  # "AA AA 55" should still sync on the second AA
                self._state = self._WAIT_SYNC0
        elif state == self._TYPE:
            self._type = byte
            self._state = self._SEQ
        elif state == self._SEQ:
            self._seq = byte
            self._state = self._LEN
        elif state == self._LEN:
            if byte > MAX_PAYLOAD:
                self._reset()
            else:
                self._len = byte
                self._payload = bytearray()
                self._state = self._PAYLOAD if byte else self._CRC
        elif state == self._PAYLOAD:
            self._payload.append(byte)
            if len(self._payload) == self._len:
                self._state = self._CRC
        elif state == self._CRC:
            body = bytes([self._type, self._seq, self._len]) + bytes(self._payload)
            frame = Frame(self._type, self._seq, bytes(self._payload))
            ok = crc8(body) == byte
            self._reset()
            if ok:
                return frame
            self.crc_errors += 1
        return None
