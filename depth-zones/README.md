# Depth zones: floor and cane filtering, IMU pitch, haptic mapping (Project Daredevil)

Building blocks for turning a RealSense depth frame into "how close is the nearest
obstacle on my left / ahead / right", without alerting on the floor or on the user's
own hands and cane, and for turning those three numbers into motor intensities for
the two bracelets. Owner: Chad.

These are **primitives**, not a finished pipeline. Nothing here has its own main loop or
talks to the camera. They are meant to be compared with `object-detection/` and merged
selectively, and they reuse that code's zone names, 33%/67% split and 0.5-3.0 m window so
they can drop in behind it.

## Where it fits (Sprint 3 plan)

| File | What it does | Story / task |
| --- | --- | --- |
| `imu_pitch.py` | Camera pitch from the D435i accelerometer, smoothed | Story 7 (floor must not alert). No sprint card yet |
| `zone_depth.py` | Floor mask from geometry, hands/cane filter from a short frame history, speckle removal, nearest distance per zone | Story 7; supports 6.1, 6.2, 8.3 |
| `haptic_map.py` | Zone distances to two 4-motor intensity vectors (left zone -> left outer pair, right zone -> right outer pair, center -> inner pair on both) | 6.7; 4.3 for the intensity bands (pending spike S3) |
| `test_*.py` | Unit tests on synthetic frames, no camera needed | |

## Usage (a sketch, not run end to end)
```python
from zone_depth import ZoneDetector
from imu_pitch import PitchEstimator
from haptic_map import HapticMapper

detector = ZoneDetector(depth_scale, intr.fy, intr.ppy, cam_height_m=1.2)  # measure the real height
pitch = PitchEstimator()
mapper = HapticMapper()                       # HapticMapper(bands=DEFAULT_BANDS) for stepped levels

# once per depth frame:
p = pitch.update(ax, ay, az)                  # latest accelerometer sample
zones = detector.process(depth_raw, p)        # {"Left": metres or None, "Center": ..., "Right": ...}
for side, motors in mapper.map(zones).items():     # "left" / "right" -> [m0, m1, m2, m3]
    if side in hub.bracelets:
        hub.bracelets[side].set_motors(motors)     # daredevil_link (source/jetson)
```
`ZoneDetector.update()` returns `(depth_m, ignore_mask)` if you want to keep your own zone
logic and only borrow the floor and body filtering: pass the mask to
`process_depth_frame(depth_m, ignore)`, which has the same name and return value as the
function in `object-detection/object_detection.py`.

## Tests
```bash
pip install -r requirements.txt
python -m pytest
```
63 tests. Ten of them (`test_link_contract.py`) check that the mapper's output goes through
`daredevil_link`'s `Bracelet.set_motors()` unchanged; they skip themselves if `source/jetson/`
is not next to this folder. Run on Python 3.9 / NumPy 2.0.2 and Python 3.10 / NumPy 2.2.6
with OpenCV 5.0.

## What is verified and what is not
Verified: the logic, on synthetic frames (flat floor, boxes, noise, a static "hand", an
approaching obstacle, zone edges, range window, ring-buffer wrap, the link contract).

**Not verified on hardware** (grep for `UNVERIFIED` and `PLACEHOLDER` in the code):
- IMU axes and sign, and whether the IMU streams on the Jetson at all.
- The floor model against real depth data: flat floor, no roll, camera height measured on the
  real harness.
- All thresholds (floor tolerance, hands/cane window and range, speckle kernel).
- Frame time on the Jetson (about 10 ms/frame at 640x480 on a development machine's CPU).
- Motor order, minimum PWM and band values for the bracelets (spike S3, task 6.8).

## Known limits (by design)
- A static object nearer than 0.8 m is treated as "body" once the 10-frame window fills, and
  nothing is filtered for the first 10 frames after start-up.
- A 3x3 speckle filter can erase objects only 1-2 pixels wide. Test a thin pole.
- Stairs and drop-offs are out of scope for 1.0. `dropoff_mask()` is only a prototype for S4.
- Nothing is logged and no pulse patterns are generated here.
