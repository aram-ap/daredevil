"""Ask the bracelets to play one of their built-in vibration patterns.

Run from source/jetson:
  python3 -m examples.play_pattern low_battery --port "/dev/cu.usbmodem*"   # USB on a Mac
  python3 -m examples.play_pattern boot                                     # USB on the Jetson
  python3 -m examples.play_pattern link_lost --wifi                         # Wi-Fi

The patterns themselves are defined in source/esp32/include/patterns.h.
"""

from __future__ import annotations

import argparse
import time
from typing import Optional, Sequence

from daredevil_link import protocol as p
from daredevil_link.bracelet import DEFAULT_PORT_GLOB, Bracelet, find_bracelets
from daredevil_link.udp import DEFAULT_PORT

from examples.motor_sweep import find_over_wifi

ACK_TIMEOUT_S = 0.5
STATUS_NAMES = {
    p.STATUS_OK: "OK",
    p.STATUS_BAD_LENGTH: "bad length",
    p.STATUS_UNKNOWN_TYPE: "unknown type (firmware older than 0.3? reflash it)",
    p.STATUS_BAD_ARGUMENT: "unknown pattern id (firmware and Python disagree on patterns)",
}


def wait_for_ack(b: Bracelet, seq: int) -> Optional[int]:
    """Return the ACK status for this seq, or None if no ACK arrived in time."""
    deadline = time.monotonic() + ACK_TIMEOUT_S
    while time.monotonic() < deadline:
        for frame in b.poll():
            if frame.type == p.MSG_ACK and frame.seq == seq and len(frame.payload) >= 2:
                return frame.payload[1]
        time.sleep(0.001)
    return None


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pattern", choices=sorted(p.PATTERNS), help="pattern to play")
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

    try:
        for side, b in bracelets.items():
            seq = b.play_pattern(p.PATTERNS[args.pattern])
            status = wait_for_ack(b, seq)
            if status is None:
                result = "no ACK (is the link up?)"
            else:
                result = STATUS_NAMES.get(status, f"status {status}")
            print(f"{side} ({b.transport!r}, fw {b.identity.fw_version}): {args.pattern} -> {result}")
    finally:
        # Close only the links. Bracelet.close() would also send "motors off",
        # which arms the watchdog, so 0.5 s later the bracelet would play the
        # link-lost pattern over the one requested here.
        for b in bracelets.values():
            b.transport.close()
        if hub is not None:
            hub.close()


if __name__ == "__main__":
    main()
