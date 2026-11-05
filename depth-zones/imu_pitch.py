"""imu_pitch.py -- camera pitch from the D435i's accelerometer.

Story/task:     user story 7 (floor must not trigger alerts); feeds zone_depth.py.
                No sprint card yet: propose one (e.g. under 6.1 or 8.3).
Needs hardware: the math, no; reading the real IMU, yes.
Verified:       the math only (see test_imu_pitch.py). Axes, sign and streaming on
                the Jetson are UNVERIFIED (see below).

The floor model in zone_depth.py needs the camera's downward pitch every frame.
The D435i has a built-in IMU, readable through the same pyrealsense2 pipeline the
depth stream already uses.

Frame convention assumed here (librealsense motion frames, mapped to the camera
frame): X right, Y down, Z forward (the way the lens points). An accelerometer at
rest reports the reaction to gravity, so a LEVEL camera reads ay ~ -9.81 and
tilting the lens DOWN by theta gives (ay, az) = (-g*cos(theta), -g*sin(theta)),
hence  pitch_down = atan2(-az, -ay).

UNVERIFIED(hw): sign and axis conventions MUST be checked on the real camera.
Hold it level (pitch ~ 0), then tilt the lens down by hand: pitch should go
positive. If it goes negative, pass sign=-1 to PitchEstimator. Also confirm that:
  * the IMU streams at all on the Jetson (rs-enumerate-devices, rs-motion); that
    depends on how librealsense was built there;
  * the small rotation between the IMU and the depth camera can be ignored
    (check with the stream profiles' get_extrinsics_to()); it is ignored here.

Limitation: while walking, footsteps add acceleration on top of gravity, so a raw
accelerometer angle is noisy. PitchEstimator low-pass filters the gravity vector.
A gyro + accelerometer complementary filter is the next step if that isn't enough.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple


def pitch_from_accel(ax: float, ay: float, az: float) -> float:
    """Downward pitch (rad) of the lens from one accelerometer sample (m/s^2)."""
    return math.atan2(-az, -ay)


def roll_from_accel(ax: float, ay: float, az: float) -> float:
    """Roll (rad) about the lens axis. The floor model assumes ~0; use this to
    check that assumption, or to add a roll term later."""
    return math.atan2(ax, -ay)


class PitchEstimator:
    """Exponential moving average of the accelerometer (gravity) vector -> pitch.

    alpha: weight of the newest sample (0..1). Smaller = smoother but slower to
           follow real tilt. At ~63 Hz, alpha=0.05 settles in roughly 0.3 s.
    sign:  +1 or -1; flip if the bench check shows the wrong direction.
    """

    def __init__(self, alpha: float = 0.05, sign: int = +1) -> None:
        self.alpha = alpha
        self.sign = sign
        self._g: Optional[Tuple[float, float, float]] = None   # filtered (ax, ay, az)

    def update(self, ax: float, ay: float, az: float) -> float:
        if self._g is None:
            self._g = (ax, ay, az)
        else:
            a = self.alpha
            self._g = tuple((1 - a) * old + a * new
                            for old, new in zip(self._g, (ax, ay, az)))
        return self.pitch

    @property
    def pitch(self) -> float:
        """Latest filtered pitch in radians; 0.0 before the first sample."""
        if self._g is None:
            return 0.0
        return self.sign * pitch_from_accel(*self._g)


# Sketch of reading it with pyrealsense2 (not run/tested here -- needs hardware):
#   cfg.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
#   cfg.enable_stream(rs.stream.accel, rs.format.motion_xyz32f, 63)
#   frames = pipe.wait_for_frames()
#   for f in frames:
#       if f.is_motion_frame() and f.get_profile().stream_type() == rs.stream.accel:
#           a = f.as_motion_frame().get_motion_data()      # a.x, a.y, a.z
#           pitch = est.update(a.x, a.y, a.z)
#   zones = detector.process(np.asanyarray(frames.get_depth_frame().get_data()), pitch)
# Check the IMU rates your unit supports with:  rs-enumerate-devices -c
