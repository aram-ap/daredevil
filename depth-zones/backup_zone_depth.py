"""
Slices a filtered 3D horizontal depth map into spatial zones (Left, Center, Right),
computes reliable obstacle distances per zone using percentile + minimum surface-area
gating, and feeds confirmed distances into the haptic mapping pipeline.
"""

import time
import argparse
import numpy as np

from obstacle_filter import ObstacleDepthFilter

# Optional imports from sibling modules in depth-zones/
try:
    import pyrealsense2 as rs
    HAS_REALSENSE = True
except ImportError:
    HAS_REALSENSE = False

try:
    import imu_pitch
    HAS_IMU_MODULE = True
except ImportError:
    HAS_IMU_MODULE = False

try:
    import haptic_map
    HAS_HAPTIC_MODULE = True
except ImportError:
    HAS_HAPTIC_MODULE = False


# Default spatial zone names (left-to-right across the frame)
ZONE_NAMES = ("left", "center", "right")
MIN_VALID_DEPTH_M = 0.15
MAX_VALID_DEPTH_M = 4.00


def compute_zone_distance(
    zone_roi: np.ndarray,
    min_fill_ratio: float = 0.08,
    min_depth_m: float = MIN_VALID_DEPTH_M,
    max_depth_m: float = MAX_VALID_DEPTH_M,
    percentile: float = 10.0,
) -> float:
    """
    Computes the obstacle distance (in meters) for a single zone slice.

    Requires at least `min_fill_ratio` (default 8%) of the zone's pixels to contain
    valid obstacle measurements so thin cane shafts or stereo noise spikes are ignored.
    Returns float('inf') if no valid obstacle is present.
    """
    if zone_roi.size == 0:
        return float("inf")

    valid_pixels = zone_roi[(zone_roi >= min_depth_m) & (zone_roi <= max_depth_m)]

    # Area gate: ignore thin vertical/diagonal cane shafts (< 8% of zone area)
    min_required_pixels = int(zone_roi.size * min_fill_ratio)
    if valid_pixels.size < max(1, min_required_pixels):
        return float("inf")

    # 10th-percentile distance gives the closest obstacle surface without single-pixel noise
    return float(np.percentile(valid_pixels, percentile))


def compute_zone_depths(
    clean_depth_m: np.ndarray,
    zone_names: tuple = ZONE_NAMES,
    min_fill_ratio: float = 0.08,
    max_depth_m: float = MAX_VALID_DEPTH_M,
) -> dict[str, float]:
    """
    Splits a filtered depth map (H, W) horizontally into equal-width spatial zones
    and returns a dict mapping each zone name to its obstacle distance in meters.
    """
    if clean_depth_m.ndim != 2:
        raise ValueError(f"Expected 2D depth array, got shape {clean_depth_m.shape}")

    _, width = clean_depth_m.shape
    num_zones = len(zone_names)
    col_edges = np.linspace(0, width, num_zones + 1, dtype=int)

    zone_distances: dict[str, float] = {}
    for idx, name in enumerate(zone_names):
        c_start, c_end = col_edges[idx], col_edges[idx + 1]
        zone_roi = clean_depth_m[:, c_start:c_end]
        zone_distances[name] = compute_zone_distance(
            zone_roi,
            min_fill_ratio=min_fill_ratio,
            max_depth_m=max_depth_m,
        )

    return zone_distances


class MultiFrameZoneTracker:
    """
    Stabilizes haptic feedback by requiring an obstacle to be present in a zone
    for `confirm_frames` consecutive frames before triggering a close distance.
    """

    def __init__(
        self,
        zone_names: tuple = ZONE_NAMES,
        trigger_dist_m: float = 2.0,
        confirm_frames: int = 3,
    ):
        self.zone_names = zone_names
        self.trigger_dist_m = trigger_dist_m
        self.confirm_frames = confirm_frames
        self.hit_counts = {name: 0 for name in zone_names}

    def update(self, raw_zone_depths: dict[str, float]) -> dict[str, float]:
        confirmed: dict[str, float] = {}
        for name in self.zone_names:
            dist = raw_zone_depths.get(name, float("inf"))
            if dist <= self.trigger_dist_m:
                self.hit_counts[name] = min(
                    self.confirm_frames, self.hit_counts[name] + 1
                )
            else:
                self.hit_counts[name] = 0

            if self.hit_counts[name] >= self.confirm_frames:
                confirmed[name] = dist
            else:
                confirmed[name] = float("inf")
        return confirmed


class ZoneDepthPipeline:
    """
    Full frame-to-zone pipeline combining:
    1. ObstacleDepthFilter (3D floor removal + wall preservation + ego-hand/cane filter)
    2. Spatial zone slicing with 8% minimum area gating
    3. Multi-frame confirmation
    """

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        fy: float = 382.0,
        cy: float = 240.0,
        cam_height_m: float = 1.35,
        floor_clearance_m: float = 0.10,
        min_fill_ratio: float = 0.08,
        confirm_frames: int = 3,
    ):
        self.depth_filter = ObstacleDepthFilter(
            width=width,
            height=height,
            fy=fy,
            cy=cy,
            cam_height_m=cam_height_m,
            floor_clearance_m=floor_clearance_m,
        )
        self.min_fill_ratio = min_fill_ratio
        self.tracker = MultiFrameZoneTracker(confirm_frames=confirm_frames)

    def process_frame(
        self,
        depth_m: np.ndarray,
        pitch_deg: float = 0.0,
        yolo_mask: np.ndarray = None,
        yolo_boxes: list = None,
    ) -> tuple[np.ndarray, dict[str, float], dict[str, float]]:
        """
        Processes a single depth frame (in meters).
        Returns:
            clean_depth_m: (H, W) filtered horizontal distance map
            raw_zones: dict of instantaneous zone distances {'left': m, 'center': m, 'right': m}
            confirmed_zones: dict of multi-frame confirmed zone distances
        """
        clean_depth_m = self.depth_filter.filter_frame(
            depth_m=depth_m,
            pitch_deg=pitch_deg,
            yolo_mask=yolo_mask,
            yolo_boxes=yolo_boxes,
        )
        raw_zones = compute_zone_depths(
            clean_depth_m, min_fill_ratio=self.min_fill_ratio
        )
        confirmed_zones = self.tracker.update(raw_zones)
        return clean_depth_m, raw_zones, confirmed_zones


def run_self_test():
    """
    Runs a synthetic verification test when no RealSense D435i is attached.
    Tests that:
    - Left zone registers a 1.20m vertical wall.
    - Center zone ignores a close hand (0.35m) AND ignores a thin 6px cane shaft (0.90m).
    - Right zone ignores the flat floor.
    """
    print("Running ZoneDepthPipeline synthetic self-test...")
    pipeline = ZoneDepthPipeline(width=640, height=480, cam_height_m=1.35, confirm_frames=3)

    # Build synthetic 640x480 depth frame
    test_depth = np.zeros((480, 640), dtype=np.float32)

    # 1. Left zone (cols 0..213): Vertical wall at 1.20m
    test_depth[:, :200] = 1.20

    # 2. Center & Right zones (cols 200..640): Flat floor at y_down = 1.35m
    for v in range(260, 480):
        test_depth[v, 200:] = 1.35 / pipeline.depth_filter.v_norm[v, 0]

    # 3. Center zone: User's hand in ego-pocket (0.35m) + thin 6-pixel cane shaft at 0.90m
    test_depth[350:420, 280:360] = 0.35  # Ego-hand
    test_depth[220:460, 317:323] = 0.90  # Thin cane shaft (< 8% of center zone area)

    # Feed 3 consecutive frames to satisfy multi-frame confirmation
    for i in range(1, 4):
        _, raw_zones, confirmed_zones = pipeline.process_frame(test_depth, pitch_deg=0.0)
        print(
            f"Frame {i} | Raw: {raw_zones} | Confirmed: {confirmed_zones}"
        )

    print("\nVerification Summary:")
    print(f"  Left zone (wall at 1.2m):       {confirmed_zones['left']:.2f} m (expected ~1.20 m)")
    print(f"  Center zone (hand + cane only): {confirmed_zones['center']} (expected inf)")
    print(f"  Right zone (open floor only):   {confirmed_zones['right']} (expected inf)")


def run_live_realsense(cam_height_m: float = 1.35):
    """
    Streams live 640x480 depth + IMU from an Intel RealSense D435i.
    """
    if not HAS_REALSENSE:
        print("pyrealsense2 not installed in this environment. Running self-test instead.\n")
        run_self_test()
        return

    rs_pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.accel, rs.format.motion_xyz32f, 200)

    try:
        profile = rs_pipeline.start(config)
    except Exception as exc:
        print(f"No RealSense D435i detected ({exc}). Running self-test instead.\n")
        run_self_test()
        return

    depth_sensor = profile.get_device().first_depth_sensor()
    depth_scale = depth_sensor.get_depth_scale()

    depth_stream = profile.get_stream(rs.stream.depth).as_video_stream_profile()
    intr = depth_stream.get_intrinsics()

    pipeline = ZoneDepthPipeline(
        width=intr.width,
        height=intr.height,
        fy=intr.fy,
        cy=intr.ppy,
        cam_height_m=cam_height_m,
    )

    print("Live D435i zone depth stream started. Press Ctrl+C to stop.")
    pitch_deg = 0.0

    try:
        while True:
            frames = rs_pipeline.wait_for_frames()
            depth_frame = frames.get_depth_frame()
            if not depth_frame:
                continue

            # Extract pitch from accel frame if available
            accel_frame = frames.first_or_default(rs.stream.accel)
            if accel_frame:
                accel_data = accel_frame.as_motion_frame().get_motion_data()
                # Pitch downward is positive when camera tilts toward the floor
                pitch_deg = float(
                    np.rad2deg(
                        np.arctan2(-accel_data.z, np.hypot(accel_data.x, accel_data.y))
                    )
                )

            raw_depth = np.asanyarray(depth_frame.get_data(), dtype=np.float32)
            depth_m = raw_depth * depth_scale

            _, _, confirmed = pipeline.process_frame(depth_m, pitch_deg=pitch_deg)
            print(
                f"\rPitch: {pitch_deg:+5.1f} deg | "
                f"Left: {confirmed['left']:4.2f}m | "
                f"Center: {confirmed['center']:4.2f}m | "
                f"Right: {confirmed['right']:4.2f}m",
                end="",
                flush=True,
            )
    except KeyboardInterrupt:
        print("\nStopping D435i stream.")
    finally:
        rs_pipeline.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run D435i Zone Depth Pipeline")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run synthetic self-test without hardware",
    )
    parser.add_argument(
        "--cam-height",
        type=float,
        default=1.35,
        help="Camera height above floor in meters (default: 1.35)",
    )
    args = parser.parse_args()

    if args.test:
        run_self_test()
    else:
        run_live_realsense(cam_height_m=args.cam_height)