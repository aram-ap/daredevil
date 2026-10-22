import unittest

from daredevil_link import protocol as p


class Crc8Test(unittest.TestCase):
    def test_standard_check_value(self):
        # Published check value for CRC-8 (poly 0x07, init 0x00).
        self.assertEqual(p.crc8(b"123456789"), 0xF4)


class FrameTest(unittest.TestCase):
    def test_round_trip(self):
        raw = p.encode_frame(p.MSG_SET_MOTORS, 7, bytes([0, 64, 128, 255]))
        frames = p.FrameParser().feed(raw)
        self.assertEqual(frames, [p.Frame(p.MSG_SET_MOTORS, 7, bytes([0, 64, 128, 255]))])

    def test_empty_payload(self):
        raw = p.encode_frame(p.MSG_HEARTBEAT, 255)
        self.assertEqual(len(raw), p.HEADER_LEN + 1)
        self.assertEqual(p.FrameParser().feed(raw), [p.Frame(p.MSG_HEARTBEAT, 255)])

    def test_byte_at_a_time(self):
        raw = p.encode_frame(p.MSG_IDENTIFY, 1)
        parser = p.FrameParser()
        frames = []
        for b in raw:
            frames += parser.feed(bytes([b]))
        self.assertEqual(frames, [p.Frame(p.MSG_IDENTIFY, 1)])

    def test_corrupt_crc_is_dropped(self):
        raw = bytearray(p.encode_frame(p.MSG_SET_MOTORS, 3, bytes(4)))
        raw[6] ^= 0xFF  # flip a payload byte
        parser = p.FrameParser()
        self.assertEqual(parser.feed(bytes(raw)), [])
        self.assertEqual(parser.crc_errors, 1)

    def test_resync_after_garbage(self):
        good = p.encode_frame(p.MSG_HEARTBEAT, 9)
        stream = b"\x00\x13\xAA\x42" + b"\xAA" + good
        self.assertEqual(p.FrameParser().feed(stream), [p.Frame(p.MSG_HEARTBEAT, 9)])

    def test_oversized_length_is_rejected(self):
        bogus = bytes([p.SYNC0, p.SYNC1, p.MSG_SET_MOTORS, 0, p.MAX_PAYLOAD + 1])
        good = p.encode_frame(p.MSG_HEARTBEAT, 2)
        self.assertEqual(p.FrameParser().feed(bogus + good), [p.Frame(p.MSG_HEARTBEAT, 2)])

    def test_payload_too_long_raises(self):
        with self.assertRaises(ValueError):
            p.encode_frame(p.MSG_SET_MOTORS, 0, bytes(p.MAX_PAYLOAD + 1))


if __name__ == "__main__":
    unittest.main()
