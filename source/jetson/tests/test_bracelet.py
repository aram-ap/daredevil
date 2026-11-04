"""Bracelet behaviour over any transport (no hardware, no pyserial)."""

import unittest

from daredevil_link import protocol as p
from daredevil_link.bracelet import Bracelet, Identity

from fakes import FakeBracelet, FakeTransport


class SendTest(unittest.TestCase):
    def test_set_motors_writes_one_frame(self):
        t = FakeTransport()
        Bracelet(t).set_motors([0, 64, 128, 255])
        self.assertEqual(t.frames_written(), [p.Frame(p.MSG_SET_MOTORS, 0, bytes([0, 64, 128, 255]))])

    def test_seq_counts_up_and_wraps(self):
        t = FakeTransport()
        b = Bracelet(t)
        for _ in range(257):
            b.heartbeat()
        seqs = [f.seq for f in t.frames_written()]
        self.assertEqual(seqs[:3], [0, 1, 2])
        self.assertEqual(seqs[255:], [255, 0])

    def test_bad_intensities_raise_and_send_nothing(self):
        t = FakeTransport()
        b = Bracelet(t)
        for bad in ([1, 2, 3], [1, 2, 3, 4, 5], [0, 0, 0, 256], [0, 0, 0, -1]):
            with self.assertRaises(ValueError):
                b.set_motors(bad)
        self.assertEqual(t.written, [])


class ReceiveTest(unittest.TestCase):
    def test_poll_returns_frames_split_across_reads(self):
        t = FakeTransport()
        b = Bracelet(t)
        ack = p.encode_frame(p.MSG_ACK, 9, bytes([p.MSG_SET_MOTORS, p.STATUS_OK]))
        t.push(ack[:3])
        self.assertEqual(b.poll(), [])
        t.push(ack[3:])
        self.assertEqual(b.poll(), [p.Frame(p.MSG_ACK, 9, bytes([p.MSG_SET_MOTORS, p.STATUS_OK]))])

    def test_identify_reads_side_and_version(self):
        b = Bracelet(FakeTransport(responder=FakeBracelet(side=p.SIDE_RIGHT, fw=(0, 1))))
        identity = b.identify(timeout=0.5)
        self.assertEqual(identity, Identity(side=p.SIDE_RIGHT, fw_version="0.1", num_motors=4))
        self.assertEqual(identity.side_name, "right")
        self.assertEqual(b.identity, identity)

    def test_identify_times_out_without_reply(self):
        b = Bracelet(FakeTransport())
        with self.assertRaises(TimeoutError):
            b.identify(timeout=0.05)


class CloseTest(unittest.TestCase):
    def test_close_stops_motors_then_closes_transport(self):
        t = FakeTransport()
        Bracelet(t).close()
        self.assertEqual(t.frames_written()[-1].type, p.MSG_SET_MOTORS)
        self.assertEqual(t.frames_written()[-1].payload, bytes(p.NUM_MOTORS))
        self.assertTrue(t.closed)


if __name__ == "__main__":
    unittest.main()
