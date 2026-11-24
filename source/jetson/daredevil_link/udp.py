"""Wi-Fi link: one UDP socket on the Jetson, shared by every bracelet.

The bracelets join the Jetson's hotspot and send their IDENTITY frame to it
until commands start arriving. The hub learns each bracelet's address from
those announcements; one UDP datagram carries one frame.
"""

from __future__ import annotations

import socket
import time
from typing import Callable, Dict, Set, Tuple

from . import protocol as p
from .bracelet import Bracelet, Identity

# PLACEHOLDER port -- must match the firmware.
DEFAULT_PORT = 5005
MAX_DATAGRAM = 512
# Unlinked bracelets announce once a second. If a different IP claims a side
# while the current owner announced less than this long ago, two boards were
# flashed with the same side.
CONFLICT_WINDOW_S = 3.0

Address = Tuple[str, int]


class UdpTransport:
    """The link to one bracelet: writes go to its address, reads return what it sent."""

    def __init__(self, hub: "UdpHub", address: Address) -> None:
        self._hub = hub
        self.address = address
        self._inbox = bytearray()

    def __repr__(self) -> str:
        return f"UdpTransport({self.address!r})"

    def write(self, data: bytes) -> None:
        self._hub._sendto(data, self.address)

    def read(self) -> bytes:
        self._hub.poll()
        data = bytes(self._inbox)
        self._inbox.clear()
        return data

    def close(self) -> None:
        pass  # the socket belongs to the hub

    def _deliver(self, data: bytes) -> None:
        self._inbox += data


class UdpHub:
    def __init__(
        self,
        bind: Address = ("0.0.0.0", DEFAULT_PORT),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(bind)
        self._sock.setblocking(False)
        self._clock = clock
        self.bracelets: Dict[str, Bracelet] = {}
        # side -> every IP seen claiming it at the same time (a setup mistake)
        self.conflicts: Dict[str, Set[str]] = {}
        self._by_address: Dict[Address, UdpTransport] = {}
        self._last_announce: Dict[str, float] = {}  # IP -> clock() of its last announcement

    @property
    def address(self) -> Address:
        return self._sock.getsockname()

    def peer_address(self, side_name: str) -> Address:
        return self.bracelets[side_name].transport.address

    def poll(self) -> None:
        """Read every waiting datagram: route known senders, register announcements."""
        while True:
            try:
                data, addr = self._sock.recvfrom(MAX_DATAGRAM)
            except BlockingIOError:
                return
            self._handle(data, addr)

    def close(self) -> None:
        self._sock.close()

    def _handle(self, data: bytes, addr: Address) -> None:
        transport = self._by_address.get(addr)
        if transport is not None:
            # Known bracelet: hand it everything, including IDENTITY replies
            # that its identify() is waiting for. Still note when it announced,
            # so a second board claiming its side is seen as a conflict.
            if any(f.type == p.MSG_IDENTITY for f in p.FrameParser().feed(data)):
                self._last_announce[addr[0]] = self._clock()
            transport._deliver(data)
            return
        # Unknown address: only a valid announcement registers it; the
        # announcement itself is not delivered as a reply. Anything else is dropped.
        for frame in p.FrameParser().feed(data):
            if frame.type == p.MSG_IDENTITY and len(frame.payload) >= 4:
                self._register(Identity.from_payload(frame.payload), addr)

    def _register(self, identity: Identity, addr: Address) -> None:
        name = identity.side_name
        if name == "unknown":
            return
        now = self._clock()
        ip = addr[0]
        existing = self.bracelets.get(name)
        if existing is None:
            self._last_announce[ip] = now
            transport = UdpTransport(self, addr)
            self._by_address[addr] = transport
            self.bracelets[name] = Bracelet(transport, identity)
            return
        owner_ip = existing.transport.address[0]
        owner_seen = self._last_announce.get(owner_ip)
        self._last_announce[ip] = now
        if ip != owner_ip and owner_seen is not None and now - owner_seen < CONFLICT_WINDOW_S:
            # Another board is announcing the same side while the owner is
            # still announcing: two boards were flashed with the same side.
            # Keep the first one so commands don't bounce between boards.
            self.conflicts.setdefault(name, set()).update({owner_ip, ip})
            return
        # Same side announcing again, possibly from a new address after a reboot
        # (same IP, new port) or a replaced board (old one went quiet): keep the
        # Bracelet object so code holding it keeps working.
        transport = existing.transport
        self._by_address.pop(transport.address, None)
        transport.address = addr
        self._by_address[addr] = transport
        existing.identity = identity

    def _sendto(self, data: bytes, addr: Address) -> None:
        self._sock.sendto(data, addr)
