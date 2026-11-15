"""Bench test: find the bracelets, pulse each motor in turn, report link health.

Run from source/jetson:
  python3 -m examples.motor_sweep                               # USB (/dev/ttyACM*)
  python3 -m examples.motor_sweep --port "/dev/cu.usbmodem*"    # USB on a Mac
  python3 -m examples.motor_sweep --wifi                        # Wi-Fi (Jetson hotspot)

At the end it prints, per bracelet, how many commands were sent, ACKed, lost
or rejected, and the ACK round-trip time.
"""

from __future__ import annotations

import argparse
import time
from typing import Dict, Optional, Sequence, Tuple

from daredevil_link import protocol as p
from daredevil_link.bracelet import DEFAULT_PORT_GLOB, Bracelet, find_bracelets
from daredevil_link.stats import AckTracker
from daredevil_link.udp import DEFAULT_PORT, UdpHub

SEND_HZ = 20
ON_INTENSITY = 180
SECONDS_PER_MOTOR = 1.0
# Bracelets announce once a second; after the first one appears, give the
# other one this long to show up too.
EXTRA_WAIT_S = 1.5


def find_over_wifi(udp_port: int, wait: float) -> Tuple[UdpHub, Dict[str, Bracelet]]:
    hub = UdpHub(("0.0.0.0", udp_port))
    print(f"Listening for bracelet announcements on UDP {udp_port} (up to {wait:.0f} s)...")
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline and len(hub.bracelets) < 2:
        hub.poll()
        if hub.bracelets:
            deadline = min(deadline, time.monotonic() + EXTRA_WAIT_S)
        time.sleep(0.05)
    return hub, dict(hub.bracelets)


def poll_until(deadline: float, bracelets: Dict[str, Bracelet], trackers: Dict[str, AckTracker]) -> None:
    """Collect ACKs until the deadline, checking every ~1 ms for accurate round-trip times."""
    while True:
        for side, b in bracelets.items():
            for frame in b.poll():
                trackers[side].received(frame, time.monotonic())
            trackers[side].expire(time.monotonic())
        if time.monotonic() >= deadline:
            return
        time.sleep(0.001)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wifi", action="store_true", help="use Wi-Fi (UDP) instead of USB")
    parser.add_argument("--port", default=DEFAULT_PORT_GLOB, help=f"USB serial ports to try (default {DEFAULT_PORT_GLOB})")
    parser.add_argument("--udp-port", type=int, default=DEFAULT_PORT, help=f"UDP port for --wifi (default {DEFAULT_PORT})")
    parser.add_argument("--wait", type=float, default=5.0, help="seconds to wait for Wi-Fi announcements (default 5)")
    args = parser.parse_args(argv)

    hub = None
    if args.wifi:
        hub, bracelets = find_over_wifi(args.udp_port, args.wait)
        where = f"UDP port {args.udp_port}"
    else:
        bracelets = find_bracelets(args.port)
        where = args.port
    if not bracelets:
        print(f"No bracelets found on {where}")
        if hub is not None:
            hub.close()
        return

    for side, b in bracelets.items():
        ident = b.identity
        print(f"{side}: {b.transport!r} fw {ident.fw_version}, {ident.num_motors} motors")
        if ident.num_motors != p.NUM_MOTORS:
            print(f"  WARNING: firmware has {ident.num_motors} motors, Jetson expects {p.NUM_MOTORS}")

    trackers = {side: AckTracker() for side in bracelets}
    try:
        for motor in range(p.NUM_MOTORS):
            intensities = [0] * p.NUM_MOTORS
            intensities[motor] = ON_INTENSITY
            print(f"motor {motor} on")
            end = time.monotonic() + SECONDS_PER_MOTOR
            # Resend continuously: the bracelet turns motors off if it hears
            # nothing for 500 ms.
            while time.monotonic() < end:
                for side, b in bracelets.items():
                    trackers[side].sent(b.set_motors(intensities), time.monotonic())
                poll_until(time.monotonic() + 1 / SEND_HZ, bracelets, trackers)
        # Give the last commands time to be answered before counting them lost.
        poll_until(time.monotonic() + trackers[next(iter(trackers))].timeout + 0.01, bracelets, trackers)
    finally:
        for b in bracelets.values():
            b.close()
        if hub is not None:
            hub.close()

    print("Link health:")
    for side, tracker in trackers.items():
        print(f"  {side}: {tracker.stats()}")


if __name__ == "__main__":
    main()
