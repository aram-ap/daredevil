"""Bench test: find connected bracelets and pulse each motor in turn.

Run from source/jetson:  python3 -m examples.motor_sweep
"""

import time

from daredevil_link import protocol as p
from daredevil_link.bracelet import find_bracelets

SEND_HZ = 20
ON_INTENSITY = 180
SECONDS_PER_MOTOR = 1.0


def main() -> None:
    bracelets = find_bracelets()
    if not bracelets:
        print("No bracelets found on /dev/ttyACM*")
        return
    for side, b in bracelets.items():
        print(f"{side}: {b.port} fw {b.identity.fw_version}, {b.identity.num_motors} motors")

    acks = 0
    try:
        for motor in range(p.NUM_MOTORS):
            intensities = [0] * p.NUM_MOTORS
            intensities[motor] = ON_INTENSITY
            print(f"motor {motor} on")
            end = time.monotonic() + SECONDS_PER_MOTOR
            # Resend continuously: the bracelet turns motors off if it hears
            # nothing for 500 ms.
            while time.monotonic() < end:
                for b in bracelets.values():
                    b.set_motors(intensities)
                    acks += sum(f.type == p.MSG_ACK for f in b.poll())
                time.sleep(1 / SEND_HZ)
    finally:
        for b in bracelets.values():
            b.close()
    print(f"done, {acks} ACKs received")


if __name__ == "__main__":
    main()
