"""Test doubles: an in-memory transport and a simulated bracelet."""

from daredevil_link import protocol as p


class FakeBracelet:
    """Answers frames the way the firmware does.

    SET_MOTORS and HEARTBEAT get an ACK, IDENTIFY gets an IDENTITY. Call it
    with the bytes the Jetson wrote; it returns the bytes the bracelet replies.
    """

    def __init__(self, side=p.SIDE_LEFT, fw=(0, 1), num_motors=p.NUM_MOTORS):
        self.side = side
        self.fw = fw
        self.num_motors = num_motors
        self.motors = [0] * num_motors
        self._parser = p.FrameParser()
        self._tx_seq = 0

    def identity_frame(self) -> bytes:
        payload = bytes([self.side, self.fw[0], self.fw[1], self.num_motors])
        frame = p.encode_frame(p.MSG_IDENTITY, self._tx_seq, payload)
        self._tx_seq = (self._tx_seq + 1) & 0xFF
        return frame

    def __call__(self, data: bytes) -> bytes:
        reply = b""
        for frame in self._parser.feed(data):
            if frame.type == p.MSG_SET_MOTORS:
                self.motors = list(frame.payload)
                reply += p.encode_frame(p.MSG_ACK, frame.seq, bytes([frame.type, p.STATUS_OK]))
            elif frame.type == p.MSG_HEARTBEAT:
                reply += p.encode_frame(p.MSG_ACK, frame.seq, bytes([frame.type, p.STATUS_OK]))
            elif frame.type == p.MSG_IDENTIFY:
                reply += self.identity_frame()
        return reply


class FakeTransport:
    """In-memory stand-in for a serial port or UDP link.

    Everything passed to write() is recorded in `written`. read() returns what
    was queued with push(), or what the optional responder (e.g. a FakeBracelet)
    answered to the writes.
    """

    def __init__(self, responder=None):
        self.written = []
        self.closed = False
        self._inbox = bytearray()
        self._responder = responder

    def write(self, data: bytes) -> None:
        self.written.append(bytes(data))
        if self._responder is not None:
            self.push(self._responder(bytes(data)))

    def read(self) -> bytes:
        data = bytes(self._inbox)
        self._inbox.clear()
        return data

    def push(self, data: bytes) -> None:
        self._inbox += data

    def close(self) -> None:
        self.closed = True

    def frames_written(self):
        return p.FrameParser().feed(b"".join(self.written))
