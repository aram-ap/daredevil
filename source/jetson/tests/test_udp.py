"""UDP hub: discovering bracelets and routing frames, over real localhost sockets."""

import socket
import time
import unittest

from daredevil_link import protocol as p
from daredevil_link.udp import UdpHub

from fakes import FakeBracelet


class UdpHubTest(unittest.TestCase):
    def setUp(self):
        self.hub = UdpHub(("127.0.0.1", 0))  # port 0 = let the OS pick a free port
        self.addCleanup(self.hub.close)

    # --- helpers ----------------------------------------------------------

    def fake_bracelet_socket(self):
        """A UDP socket standing in for one ESP32 on the hotspot."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))
        s.settimeout(1.0)
        self.addCleanup(s.close)
        return s

    def announce(self, sock, side):
        sock.sendto(FakeBracelet(side=side).identity_frame(), self.hub.address)

    def wait_for(self, condition, timeout=1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.hub.poll()
            if condition():
                return
            time.sleep(0.005)
        self.fail("condition not met within timeout")

    def received_frames(self, sock):
        data, _ = sock.recvfrom(256)
        return p.FrameParser().feed(data)

    # --- tests ------------------------------------------------------------

    def test_announcement_registers_bracelet_by_side(self):
        self.announce(self.fake_bracelet_socket(), p.SIDE_LEFT)
        self.wait_for(lambda: "left" in self.hub.bracelets)
        self.assertEqual(self.hub.bracelets["left"].identity.fw_version, "0.1")

    def test_commands_go_to_the_announcing_address(self):
        sock = self.fake_bracelet_socket()
        self.announce(sock, p.SIDE_LEFT)
        self.wait_for(lambda: "left" in self.hub.bracelets)

        self.hub.bracelets["left"].set_motors([1, 2, 3, 4])
        self.assertEqual(self.received_frames(sock), [p.Frame(p.MSG_SET_MOTORS, 0, bytes([1, 2, 3, 4]))])

    def test_replies_reach_only_the_matching_bracelet(self):
        left_sock, right_sock = self.fake_bracelet_socket(), self.fake_bracelet_socket()
        self.announce(left_sock, p.SIDE_LEFT)
        self.announce(right_sock, p.SIDE_RIGHT)
        self.wait_for(lambda: {"left", "right"} <= set(self.hub.bracelets))
        left, right = self.hub.bracelets["left"], self.hub.bracelets["right"]

        ack = p.encode_frame(p.MSG_ACK, 5, bytes([p.MSG_SET_MOTORS, p.STATUS_OK]))
        left_sock.sendto(ack, self.hub.address)
        got = []
        self.wait_for(lambda: got.extend(left.poll()) or got)

        self.assertEqual(got, [p.Frame(p.MSG_ACK, 5, bytes([p.MSG_SET_MOTORS, p.STATUS_OK]))])
        self.assertEqual(right.poll(), [])

    def test_unknown_senders_and_garbage_are_ignored(self):
        stranger = self.fake_bracelet_socket()
        stranger.sendto(b"not a frame at all", self.hub.address)
        stranger.sendto(p.encode_frame(p.MSG_SET_MOTORS, 0, bytes(4)), self.hub.address)
        # A real announcement sent afterwards proves the junk was already processed.
        self.announce(self.fake_bracelet_socket(), p.SIDE_RIGHT)
        self.wait_for(lambda: "right" in self.hub.bracelets)

        self.assertEqual(set(self.hub.bracelets), {"right"})

    def test_announcement_with_bad_crc_is_ignored(self):
        bad = bytearray(FakeBracelet(side=p.SIDE_LEFT).identity_frame())
        bad[-1] ^= 0xFF
        self.fake_bracelet_socket().sendto(bytes(bad), self.hub.address)
        self.announce(self.fake_bracelet_socket(), p.SIDE_RIGHT)
        self.wait_for(lambda: "right" in self.hub.bracelets)

        self.assertNotIn("left", self.hub.bracelets)

    def test_reannounce_from_new_address_moves_the_same_bracelet(self):
        old_sock, new_sock = self.fake_bracelet_socket(), self.fake_bracelet_socket()
        self.announce(old_sock, p.SIDE_LEFT)
        self.wait_for(lambda: "left" in self.hub.bracelets)
        left = self.hub.bracelets["left"]

        # e.g. the bracelet rebooted and got a new IP from the hotspot
        self.announce(new_sock, p.SIDE_LEFT)
        self.wait_for(lambda: self.hub.peer_address("left") == new_sock.getsockname())

        self.assertIs(self.hub.bracelets["left"], left)  # code holding the old object keeps working
        left.heartbeat()
        self.assertEqual(self.received_frames(new_sock)[0].type, p.MSG_HEARTBEAT)


if __name__ == "__main__":
    unittest.main()
