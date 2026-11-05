"""haptic_map.py -- zone distances -> motor intensities for the two wrist bracelets.

Story/task:     task 6.7 (map zones to motors); 4.3 (distance -> strength) for the
                intensity side, with the bands pending spike S3.
Needs hardware: no. Pure Python, unit-tested.
Verified:       logic only. Motor order, minimum PWM and band values are
                PLACEHOLDERs until tested with a wearer (S3, 6.8).

Output matches the existing Jetson-side link code (source/jetson/daredevil_link):
  * keys "left" / "right" = Identity.side_name from find_bracelets()
  * each value is a list of NUM_MOTORS ints in 0..255, ready for
    Bracelet.set_motors(list)

Per-wrist motor slots (PLACEHOLDER -- must match the MOTOR_PINS order in
source/esp32/include/config.h, which is a placeholder there too):
    index 0, 1 = OUTER pair     index 2, 3 = INNER pair
Zone -> motors:
    Left   -> left  wrist, outer pair
    Right  -> right wrist, outer pair
    Center -> inner pair on BOTH wrists ("ahead" is felt symmetrically)
"""
from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Tuple

NUM_MOTORS = 4                 # keep in sync with daredevil_link/protocol.py
OUTER = (0, 1)
INNER = (2, 3)

# Same window / PWM range as object-detection/object_detection.py (ER-1: 0.5-3 m).
# Note: the YOLO branch (yolo_object.py) uses 0.3 m as the near end instead, and
# task 8.1 decides what happens closer than 0.5 m. Align these when it is decided.
MIN_DIST_METERS = 0.5
MAX_DIST_METERS = 3.0
MIN_PWM = 50                   # PLACEHOLDER: weakest intensity the wearer can feel (S3)
MAX_PWM = 255

# PLACEHOLDER bands for SF-2 ("at least 3 steps a wearer can tell apart").
# (upper edge in metres, intensity), nearest first. Spike S3 should replace these.
DEFAULT_BANDS: Tuple[Tuple[float, int], ...] = ((1.0, 255), (2.0, 160), (3.0, 90))


def distance_to_intensity(distance_m: Optional[float]) -> int:
    """Linear 0.5-3.0 m -> 255..50 ramp. Identical to calculate_vibration_intensity()
    in object_detection.py; None (clear) -> 0."""
    if distance_m is None:
        return 0
    norm = (MAX_DIST_METERS - distance_m) / (MAX_DIST_METERS - MIN_DIST_METERS)
    return int(min(max(norm * (MAX_PWM - MIN_PWM) + MIN_PWM, 0), MAX_PWM))


class HapticMapper:
    """Turn {"Left": m|None, "Center": ..., "Right": ...} into per-wrist motor vectors.

    bands=None   -> Kaleb's continuous linear ramp (the baseline).
    bands=(...)  -> quantised levels with hysteresis, so intensity does not flicker
                    when a distance hovers on a band edge. Moving CLOSER switches to
                    the stronger band immediately; moving AWAY waits until the
                    distance clears the band edge by `hysteresis_m`.
    """

    def __init__(self, bands: Optional[Sequence[Tuple[float, int]]] = None,
                 hysteresis_m: float = 0.1) -> None:
        self.bands = tuple(bands) if bands is not None else None
        self.hysteresis_m = hysteresis_m
        self._band: Dict[str, int] = {}          # zone -> current band index

    def intensity(self, zone: str, distance_m: Optional[float]) -> int:
        if distance_m is None:
            self._band.pop(zone, None)
            return 0
        if self.bands is None:
            return distance_to_intensity(distance_m)
        new = next((i for i, (edge, _) in enumerate(self.bands) if distance_m <= edge), None)
        if new is None:                          # farther than the last band: nothing to feel
            self._band.pop(zone, None)
            return 0
        old = self._band.get(zone)
        if old is not None and new > old and distance_m <= self.bands[old][0] + self.hysteresis_m:
            new = old                            # receding, but not clearly out of the old band yet
        self._band[zone] = new
        return self.bands[new][1]

    def map(self, zones: Mapping[str, Optional[float]]) -> Dict[str, List[int]]:
        left_i = self.intensity("Left", zones.get("Left"))
        center_i = self.intensity("Center", zones.get("Center"))
        right_i = self.intensity("Right", zones.get("Right"))
        left, right = [0] * NUM_MOTORS, [0] * NUM_MOTORS
        for m in OUTER:
            left[m] = left_i
            right[m] = right_i
        for m in INNER:
            left[m] = center_i
            right[m] = center_i
        return {"left": left, "right": right}
