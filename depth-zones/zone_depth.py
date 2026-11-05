"""zone_depth.py -- depth frame -> nearest obstacle per zone, ignoring floor and hands/cane.

Story/task:     user story 7 (don't alert on the floor or my cane); supports task 6.1
                (zones), 6.2 (confirmation per zone), 8.3 (tune filtering) and OA-3.
Needs hardware: no. Pure numpy + OpenCV, unit-tested with synthetic frames.
Verified:       logic only (see test_zone_depth.py). The floor model and every
                threshold below are UNVERIFIED against real D435i data.

Conventions deliberately match code already in the repo:
  * Zone names "Left"/"Center"/"Right", the 33% / 67% split points and the
    0.5-3.0 m alert window come from object-detection/object_detection.py and
    story ER-1 in the Release Plan.
  * process_depth_frame() keeps that file's function name and its
    (distances, valid_mask) return value, plus one new optional argument
    (`ignore`), so it can be swapped in behind the existing main loop.
  * realsense-data-collection/ (collect_depth.py, depth_math.py) stays the
    single-slice baseline for camera accuracy tests. Nothing here replaces it.

Pipeline per frame (ZoneDetector.process):
    raw uint16 depth -> meters (NaN = no reading)
      -> floor mask   geometric: where SHOULD the floor be at each image row?
      -> body mask    short frame history: near AND not changing = hands / cane
      -> ignore = floor | body
      -> process_depth_frame(): range window, speckle removal, per-zone nearest
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import cv2
import numpy as np

# =======================================================================
# Constants shared with object_detection.py (same names / values on purpose)
# =======================================================================
MIN_DIST_METERS = 0.5          # ER-1: obstacles within 0.5-3 m must trigger an alert
MAX_DIST_METERS = 3.0
LEFT_ZONE_FRAC = 0.33          # Left = first 33% of the width, Right = last 33%
RIGHT_ZONE_FRAC = 0.67
ZONE_NAMES = ("Left", "Center", "Right")

# Noise guards (new). Percentile instead of min(): one low outlier can't win.
DEFAULT_PERCENTILE = 5
DEFAULT_MIN_PIXELS = 50        # evidence required per zone, in FULL-resolution pixels


# =======================================================================
# 1. Units
# =======================================================================
def to_meters(depth_raw: np.ndarray, depth_scale: float) -> np.ndarray:
    """uint16 raw depth -> float32 meters. Raw 0 ("no reading") becomes NaN,
    NOT 0 m, so a hole in the data can never look like a very close object."""
    meters = depth_raw.astype(np.float32) * depth_scale
    meters[depth_raw == 0] = np.nan
    return meters


# =======================================================================
# 2. Floor model
# =======================================================================
def expected_floor_depth(n_rows: int, fy: float, cy: float,
                         cam_height_m: float, pitch_rad: float) -> np.ndarray:
    """Expected depth (m) of a flat floor at each image row. Shape (n_rows,).

    Derivation: a pixel at row r has v = (r - cy) / fy; its viewing ray in camera
    coordinates (X right, Y down, Z forward -- the axis the depth image stores)
    is (u, v, 1). The camera is pitched DOWN by `pitch_rad`, so the world-down
    component of a camera-frame point (X, Y, Z) is  Y*cos(pitch) + Z*sin(pitch).
    The ray reaches the floor when that equals the camera height h:
        Z * (v*cos(pitch) + sin(pitch)) = h   ->   Z = h / (v*cos + sin)
    There is no column (u) term: with no camera roll, floor depth depends only on
    the row. Rays at or above the horizon never hit the floor -> NaN.

    fy, cy:      depth-stream intrinsics (pyrealsense2: intr.fy, intr.ppy)
    pitch_rad:   positive = lens tilted down (see imu_pitch.py)

    UNVERIFIED(hw): assumes a flat floor, no camera roll, a camera height measured
    on the real harness, and a correct IMU sign. Stairs, ramps and a tilted head
    will break the assumption.
    """
    v = (np.arange(n_rows, dtype=np.float32) - cy) / fy
    denom = v * np.cos(pitch_rad) + np.sin(pitch_rad)
    z = np.full(n_rows, np.nan, dtype=np.float32)
    hits = denom > 0.02                       # tiny denominators = near-horizon, unstable
    z[hits] = cam_height_m / denom[hits]
    return z


def floor_mask(depth_m: np.ndarray, expected_rows: np.ndarray,
               tol_abs: float = 0.10, tol_rel: float = 0.05) -> np.ndarray:
    """True where the measured depth is within tolerance of the expected floor depth.
    Tolerance grows with distance (stereo depth noise grows roughly with range^2).
    PLACEHOLDER: tol_abs / tol_rel are starting values; tune on recorded walks (I6)."""
    exp = expected_rows[:, None]
    tol = np.maximum(tol_abs, tol_rel * exp)
    with np.errstate(invalid="ignore"):
        return np.abs(depth_m - exp) <= tol    # NaN compares False


def dropoff_mask(depth_m: np.ndarray, expected_rows: np.ndarray,
                 tol_abs: float = 0.10, tol_rel: float = 0.05,
                 min_drop_m: float = 0.25) -> np.ndarray:
    """True where the surface is FARTHER than the floor should be (curb down,
    stairs down). The floor mask throws this signal away; this keeps it.
    Prototype for spike S4 / backlog story OA-4. Not wired into the zone output,
    and out of scope for the 1.0 MVP unless the spike promotes it."""
    exp = expected_rows[:, None]
    tol = np.maximum(tol_abs, tol_rel * exp)
    with np.errstate(invalid="ignore"):
        return depth_m > exp + np.maximum(tol, min_drop_m)


# =======================================================================
# 3. Body (hands / cane) filter using a short frame history
# =======================================================================
class BodyFilter:
    """Flags pixels that are NEAR the camera and HOLD STILL in depth for the whole
    history window. Hands and a cane move with the user, so their range is
    constant. A real obstacle you walk toward closes in at walking speed:
    ~1.2 m/s * (10 frames / 30 fps = 0.33 s) = ~0.4 m, far above range_tol_m.

    Known blind spot (by design): something static AND within near_max_m while
    you stand still is ignored. Say so when presenting it.

    PLACEHOLDER: near_max_m, range_tol_m, n_frames and min_frac are starting
    values; tune them on recorded walks with the cane and hands in frame (I6, 8.3).

    Memory/latency: the history lives in three preallocated ring buffers that are
    written in place (no per-frame allocation or np.stack copy), and mask() is a
    handful of reductions over them. Buffer cost is 9 bytes per pixel per stored
    frame (float32 hi + float32 lo + bool near): about 28 MB for 10 frames at
    640x480, or ~7 MB with decimate=2.
    """

    def __init__(self, n_frames: int = 10, near_max_m: float = 0.8,
                 range_tol_m: float = 0.08, min_frac: float = 0.8) -> None:
        self.n_frames = n_frames
        self.near_max_m = near_max_m
        self.range_tol_m = range_tol_m
        self.min_frac = min_frac
        self._hi: Optional[np.ndarray] = None     # depth where near, else -inf
        self._lo: Optional[np.ndarray] = None     # depth where near, else +inf
        self._near: Optional[np.ndarray] = None   # bool: sample was near
        self._i = 0                               # next slot to overwrite
        self._filled = 0                          # slots holding real frames

    def update(self, depth_m: np.ndarray) -> None:
        if self._hi is None or self._lo is None or self._near is None \
                or self._hi.shape[1:] != depth_m.shape:
            shape = (self.n_frames,) + depth_m.shape
            self._hi = np.full(shape, -np.inf, np.float32)
            self._lo = np.full(shape, np.inf, np.float32)
            self._near = np.zeros(shape, bool)
            self._i = 0
            self._filled = 0
        # Local names so type checkers know the buffers exist from here on.
        hi, lo, near_buf = self._hi, self._lo, self._near
        assert hi is not None and lo is not None and near_buf is not None
        with np.errstate(invalid="ignore"):
            near = depth_m < self.near_max_m          # NaN -> False
        near_buf[self._i] = near
        # Write "depth where near, else +/-inf" straight into the slot, no temporaries.
        hi[self._i] = -np.inf
        np.copyto(hi[self._i], depth_m, where=near)
        lo[self._i] = np.inf
        np.copyto(lo[self._i], depth_m, where=near)
        self._i = (self._i + 1) % self.n_frames
        self._filled = min(self._filled + 1, self.n_frames)

    def mask(self) -> np.ndarray:
        """Boolean mask, same shape as the frames. All False until the window fills
        (so for the first n_frames frames nothing is filtered: a held cane may
        flicker an alert right after start-up)."""
        if self._hi is None or self._lo is None or self._near is None:
            return np.zeros((0, 0), bool)
        if self._filled < self.n_frames:
            return np.zeros(self._hi.shape[1:], bool)
        hi = self._hi.max(axis=0)
        lo = self._lo.min(axis=0)
        near_frac = np.count_nonzero(self._near, axis=0) / self.n_frames
        # Pixels never near have hi=-inf, lo=+inf -> hi-lo=-inf, but near_frac=0 excludes them.
        return (near_frac >= self.min_frac) & ((hi - lo) <= self.range_tol_m)


# =======================================================================
# 4. Zones
# =======================================================================
def zone_edges(width: int) -> list:
    """Column boundaries [0, left_end, right_start, width], same split as
    object_detection.py: int(width*0.33) and int(width*0.67)."""
    return [0, int(width * LEFT_ZONE_FRAC), int(width * RIGHT_ZONE_FRAC), width]


def process_depth_frame(depth_image_m: np.ndarray,
                        ignore: Optional[np.ndarray] = None, *,
                        percentile: float = DEFAULT_PERCENTILE,
                        min_pixels: int = DEFAULT_MIN_PIXELS,
                        speckle_kernel: int = 3,
                        min_range_m: float = MIN_DIST_METERS,
                        max_range_m: float = MAX_DIST_METERS,
                        ) -> Tuple[Dict[str, Optional[float]], np.ndarray]:
    """Drop-in for process_depth_frame() in object_detection.py.

    Same name, same first argument (depth in meters; zeros and NaN both count as
    "no reading"), same return: ({"Left","Center","Right"} -> metres or None, valid_mask).
    New: optional `ignore` boolean mask (floor | body) replaces the fixed
    "crop the bottom 15%" rule.

    - OpenCV morphological OPEN removes isolated pixels (stereo speckle) so one bad
      pixel can't become "the nearest object". It also erases objects thinner than
      the kernel (3 px): a 3 cm pole at 3 m is ~4 px wide at 640x480, so test thin
      obstacles before trusting this.
    - A low percentile (default 5th) instead of min() is a second noise guard, and
      min_pixels demands a minimum amount of evidence per zone.
    """
    with np.errstate(invalid="ignore"):
        valid = (np.isfinite(depth_image_m)
                 & (depth_image_m >= min_range_m) & (depth_image_m <= max_range_m))
    if ignore is not None:
        valid &= ~ignore
    if speckle_kernel > 1:
        kernel = np.ones((speckle_kernel, speckle_kernel), np.uint8)
        valid = cv2.morphologyEx(valid.astype(np.uint8), cv2.MORPH_OPEN, kernel).astype(bool)

    edges = zone_edges(depth_image_m.shape[1])
    distances: Dict[str, Optional[float]] = {}
    for name, a, b in zip(ZONE_NAMES, edges[:-1], edges[1:]):
        vals = depth_image_m[:, a:b][valid[:, a:b]]
        distances[name] = float(np.percentile(vals, percentile)) if vals.size >= min_pixels else None
    return distances, valid


# =======================================================================
# 5. Glue
# =======================================================================
class ZoneDetector:
    """One object to call per frame.

        det = ZoneDetector(depth_scale, fy, cy, cam_height_m)       # intrinsics from pyrealsense2
        zones = det.process(depth_raw_uint16, pitch_rad)            # {"Left":m|None, ...}

    Or, to keep your own zone logic and only borrow the floor/body filtering:
        depth_m, ignore = det.update(depth_raw_uint16, pitch_rad)
        zones, valid = process_depth_frame(depth_m, ignore)

    decimate: process every Nth pixel in each direction (1 = full resolution). 2 cuts
    work and memory ~4x, at the cost of thin objects: at decimate=2 an object must be
    >= ~6 full-resolution pixels wide to survive the speckle filter. Start at 1 and
    only raise it if the frame time on the Jetson is too long.
    """

    def __init__(self, depth_scale: float, fy: float, cy: float, cam_height_m: float,
                 decimate: int = 1, **body_kwargs) -> None:
        self.depth_scale = depth_scale
        self.decimate = max(1, int(decimate))
        # Striding by d divides pixel coordinates AND focal length by d.
        self.fy = fy / self.decimate
        self.cy = cy / self.decimate
        self.cam_height_m = cam_height_m
        self.body = BodyFilter(**body_kwargs)
        self.last: dict = {}                      # debug masks for visualization

    def update(self, depth_raw: np.ndarray, pitch_rad: float = 0.0
               ) -> Tuple[np.ndarray, np.ndarray]:
        """Advance the history and return (depth in meters, ignore mask) at working resolution."""
        small = depth_raw[::self.decimate, ::self.decimate]      # a view, no copy
        depth_m = to_meters(small, self.depth_scale)
        expected = expected_floor_depth(depth_m.shape[0], self.fy, self.cy,
                                        self.cam_height_m, pitch_rad)
        floor = floor_mask(depth_m, expected)
        self.body.update(depth_m)
        body = self.body.mask()
        self.last = {"depth_m": depth_m, "floor": floor, "body": body}
        return depth_m, floor | body

    def process(self, depth_raw: np.ndarray, pitch_rad: float = 0.0
                ) -> Dict[str, Optional[float]]:
        depth_m, ignore = self.update(depth_raw, pitch_rad)
        min_pixels = max(1, DEFAULT_MIN_PIXELS // (self.decimate ** 2))
        distances, valid = process_depth_frame(depth_m, ignore, min_pixels=min_pixels)
        self.last["valid"] = valid
        return distances
