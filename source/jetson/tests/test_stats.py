"""AckTracker: link health from ACKs -- round-trip time, lost and rejected commands.

Times are plain numbers (seconds) passed in, so no real clock is needed.
"""

import unittest

from daredevil_link import protocol as p
from daredevil_link.stats import AckTracker


def ack(seq, acked_type=p.MSG_SET_MOTORS, status=p.STATUS_OK):
    return p.Frame(p.MSG_ACK, seq, bytes([acked_type, status]))


class AckTrackerTest(unittest.TestCase):
    def test_matching_ack_gives_round_trip_time(self):
        t = AckTracker()
        t.sent(7, 1.000)
        self.assertAlmostEqual(t.received(ack(7), 1.012), 0.012)
        s = t.stats()
        self.assertEqual((s.sent, s.acked, s.lost), (1, 1, 0))

    def test_ignores_non_acks_unknown_seqs_and_duplicates(self):
        t = AckTracker()
        t.sent(7, 1.0)
        identity = p.Frame(p.MSG_IDENTITY, 7, bytes([0, 0, 2, 4]))
        self.assertIsNone(t.received(identity, 1.01))  # not an ACK
        self.assertIsNone(t.received(ack(9), 1.01))  # never sent
        self.assertIsNotNone(t.received(ack(7), 1.02))
        self.assertIsNone(t.received(ack(7), 1.03))  # second ACK for the same command
        self.assertEqual(t.stats().acked, 1)

    def test_unanswered_command_is_lost_after_the_timeout(self):
        t = AckTracker(timeout=0.5)
        t.sent(1, 0.0)
        t.expire(0.5)  # exactly the timeout: still waiting
        self.assertEqual(t.stats().lost, 0)
        t.expire(0.501)
        self.assertEqual(t.stats().lost, 1)
        self.assertIsNone(t.received(ack(1), 0.6))  # too late: stays lost
        self.assertEqual(t.stats().acked, 0)

    def test_reused_seq_counts_the_old_command_as_lost(self):
        # seq wraps after 256 commands; if the old one was never answered,
        # it is lost, and a new ACK belongs to the new command.
        t = AckTracker(timeout=10.0)
        t.sent(5, 0.0)
        t.sent(5, 0.1)
        self.assertEqual(t.stats().lost, 1)
        self.assertAlmostEqual(t.received(ack(5), 0.15), 0.05)

    def test_rejected_commands_are_counted(self):
        # The bracelet answered, but refused the command (e.g. wrong motor count).
        t = AckTracker()
        t.sent(3, 0.0)
        t.received(ack(3, status=p.STATUS_BAD_LENGTH), 0.01)
        s = t.stats()
        self.assertEqual((s.acked, s.rejected), (1, 1))

    def test_summary_numbers(self):
        t = AckTracker()
        for seq, rtt in enumerate([0.010, 0.020, 0.030]):
            t.sent(seq, seq * 1.0)
            t.received(ack(seq), seq * 1.0 + rtt)
        t.sent(3, 3.0)  # still waiting: neither acked nor lost yet
        s = t.stats()
        self.assertEqual((s.sent, s.acked, s.lost, s.rejected), (4, 3, 0, 0))
        self.assertAlmostEqual(s.rtt_min, 0.010)
        self.assertAlmostEqual(s.rtt_avg, 0.020)
        self.assertAlmostEqual(s.rtt_max, 0.030)

    def test_no_acks_yet_has_no_round_trip_times(self):
        s = AckTracker().stats()
        self.assertEqual((s.sent, s.acked, s.lost), (0, 0, 0))
        self.assertIsNone(s.rtt_avg)


if __name__ == "__main__":
    unittest.main()
