"""Check that the bracelets are connected and set up right, then buzz each one.

Run from source/jetson:
  python3 -m examples.check_bracelets --wifi                          # on the Jetson, over the hotspot
  python3 -m examples.check_bracelets --port "/dev/cu.usbmodem*"      # on a Mac, over USB
  python3 -m examples.check_bracelets --port /dev/cu.usbmodem14101 --expect right
                                                                      # right after flashing one board

It prints what it found and any problems (with the fix), then buzzes LEFT and
then RIGHT with a soft double pulse, so you can label which bracelet is which.
Exit code: 0 = everything looks right, 1 = something needs fixing.
"""

from __future__ import annotations

import argparse
import glob
import sys
import time
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from daredevil_link import protocol as p
from daredevil_link.bracelet import DEFAULT_PORT_GLOB, Bracelet, Identity
from daredevil_link.transport import SerialTransport
from daredevil_link.udp import DEFAULT_PORT

from examples.motor_sweep import find_over_wifi
from examples.play_pattern import STATUS_NAMES, wait_for_ack

SIDES = ("left", "right")
BUZZ_REPEATS = 2
BUZZ_GAP_S = 0.8  # the boot pattern lasts 0.4 s; leave a clear pause after it

# (where it was found: USB port or IP address, what it said about itself)
Found = List[Tuple[str, Identity]]


def assess(
    found: Found,
    conflicts: Optional[Mapping[str, Set[str]]] = None,
    expect: Sequence[str] = SIDES,
) -> List[str]:
    """Turn what was found into a list of problems, each with how to fix it.

    An empty list means the setup looks right.
    """
    by_side: Dict[str, Set[str]] = {}
    for where, ident in found:
        by_side.setdefault(ident.side_name, set()).add(where)
    for side, places in (conflicts or {}).items():
        by_side.setdefault(side, set()).update(places)

    problems = []
    for side in expect:
        if side not in by_side:
            others = ", ".join(f"{s} at {', '.join(sorted(w))}" for s, w in sorted(by_side.items()))
            seen = f" (found: {others})" if others else ""
            problems.append(f"{side} bracelet not found{seen}. Is it powered on and connected?")

    for side, places in sorted(by_side.items()):
        if side == "unknown":
            problems.append(
                f"Board at {', '.join(sorted(places))} reports an unknown side. "
                "Reflash it with: pio run -e left (or -e right) -t upload --upload-port <port>"
            )
        elif len(places) > 1:
            other = "right" if side == "left" else "left"
            problems.append(
                f"{len(places)} boards both say they are {side.upper()} ({', '.join(sorted(places))}). "
                f"Reflash one of them as {other}: "
                f"cd source/esp32 && pio run -e {other} -t upload --upload-port <its USB port>"
            )

    for where, ident in found:
        if ident.num_motors != p.NUM_MOTORS:
            problems.append(
                f"{ident.side_name} ({where}) has {ident.num_motors} motors in its firmware, "
                f"the Jetson expects {p.NUM_MOTORS}. Reflash it from the current code."
            )

    versions = sorted({(ident.side_name, ident.fw_version) for _, ident in found})
    if len({v for _, v in versions}) > 1:
        listed = ", ".join(f"{side} {version}" for side, version in versions)
        problems.append(f"Firmware versions differ ({listed}). Reflash both from the same code.")

    return problems


def side_order(sides: Iterable[str]) -> List[str]:
    """Left first, then right, then anything else."""
    rank = {side: i for i, side in enumerate(SIDES)}
    return sorted(sides, key=lambda s: (rank.get(s, len(SIDES)), s))


def buzz_each(
    bracelets: Mapping[str, Bracelet],
    repeats: int = BUZZ_REPEATS,
    gap_s: float = BUZZ_GAP_S,
    announce: Callable[[str], None] = lambda side: None,
) -> Dict[str, Optional[int]]:
    """Play the boot pattern on each bracelet in turn (left first).

    Uses PLAY_PATTERN rather than motor commands: a motor stream that stops
    makes the bracelet play its link-lost pattern 0.5 s later, which would make
    it unclear which bracelet buzzed. Returns each side's ACK status (None = no ACK).
    """
    results: Dict[str, Optional[int]] = {}
    for side in side_order(bracelets):
        b = bracelets[side]
        announce(side)
        status: Optional[int] = p.STATUS_OK
        for _ in range(repeats):
            got = wait_for_ack(b, b.play_pattern(p.PATTERN_BOOT))
            if got != p.STATUS_OK:
                status = got
            time.sleep(gap_s)
        results[side] = status
    return results


def scan_usb(port_glob: str) -> Tuple[Found, Dict[str, Bracelet]]:
    """Ask every matching USB port to identify.

    Unlike find_bracelets(), keeps every answer, so two boards that both say
    "left" are both reported. Returns (everything found, one open Bracelet per side).
    """
    found: Found = []
    bracelets: Dict[str, Bracelet] = {}
    for port in sorted(glob.glob(port_glob)):
        try:
            bracelet = Bracelet(SerialTransport(port))
        except OSError:  # serial.SerialException is an OSError
            continue
        try:
            ident = bracelet.identify()
        except TimeoutError:
            bracelet.transport.close()  # not a bracelet (or not answering)
            continue
        found.append((port, ident))
        if ident.side_name in bracelets:
            bracelet.transport.close()  # duplicate side: reported by assess()
        else:
            bracelets[ident.side_name] = bracelet
    return found, bracelets


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wifi", action="store_true", help="use Wi-Fi (UDP) instead of USB")
    parser.add_argument("--port", default=DEFAULT_PORT_GLOB, help=f"USB serial ports to try (default {DEFAULT_PORT_GLOB})")
    parser.add_argument("--udp-port", type=int, default=DEFAULT_PORT, help=f"UDP port for --wifi (default {DEFAULT_PORT})")
    parser.add_argument("--wait", type=float, default=5.0, help="seconds to wait for Wi-Fi announcements (default 5)")
    parser.add_argument("--expect", choices=["both", *SIDES], default="both", help="which side(s) must be present")
    parser.add_argument("--no-buzz", action="store_true", help="only check, don't buzz the bracelets")
    args = parser.parse_args(argv)
    expect = SIDES if args.expect == "both" else (args.expect,)

    hub = None
    conflicts: Mapping[str, Set[str]] = {}
    if args.wifi:
        hub, bracelets = find_over_wifi(args.udp_port, args.wait)
        found: Found = [(b.transport.address[0], b.identity) for b in bracelets.values()]
        conflicts = hub.conflicts
    else:
        print(f"Asking USB ports {args.port} to identify...")
        found, bracelets = scan_usb(args.port)

    try:
        print("Found:" if found else "Found: nothing")
        for where, ident in sorted(found, key=lambda f: side_order([f[1].side_name])):
            print(f"  {ident.side_name:<6} {where:<28} fw {ident.fw_version}, {ident.num_motors} motors")

        problems = assess(found, conflicts, expect)

        if bracelets and not args.no_buzz:
            print("\nBuzzing each bracelet in turn (soft double pulse)...")
            acks = buzz_each(
                bracelets,
                announce=lambda side: print(f"  {side.upper()} now -> label the bracelet that vibrates '{side.upper()}'"),
            )
            for side in side_order(acks):
                status = acks[side]
                if status is None:
                    problems.append(f"{side} did not answer the buzz request. Is the link still up?")
                elif status != p.STATUS_OK:
                    problems.append(f"{side} rejected the buzz request: {STATUS_NAMES.get(status, status)}")
    finally:
        # Close only the links: Bracelet.close() would send "motors off", which
        # arms the watchdog and triggers the link-lost pattern 0.5 s later.
        for b in bracelets.values():
            b.transport.close()
        if hub is not None:
            hub.close()

    if problems:
        print("\nProblems:")
        for i, problem in enumerate(problems, 1):
            print(f"  {i}. {problem}")
        return 1
    print("\nAll good: " + " and ".join(expect) + " found and answering.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
