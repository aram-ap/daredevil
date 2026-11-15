"""
depth-zones/run_daredevil.py

Master integration runner for Project Daredevil.
Connects D435i Depth + IMU -> ObstacleDepthFilter -> ZoneDepthPipeline
-> Haptic Mapping -> SQLite Database Logger.
"""

import sys
import time
import argparse
from pathlib import Path
import numpy as np

# Allow importing database_logger.py from the parent ~/daredevil/ directory
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from zone_depth import ZoneDepthPipeline

# Optional sibling/parent modules (graceful fallback if function names differ)
try:
    import imu_pitch
except ImportError:
    imu_pitch = None

try:
    import haptic_map
except ImportError:
    haptic_map = None

try:
    import database_logger
except ImportError:
    database_logger = None


def dist_to_pwm(dist_m: float, max_ alert_m: float = 2.0, min_alert_m: float = 0.35) -> int:
    """
    Uses haptic_map.py if available, otherwise maps distance [0.35m .. 2.0m]
    linearly to PWM duty cycle [100% .. 0%].
    """
    if haptic_map is not None:
        for fn_name in ("distance_to_pwm", "map_distance_to_pwm", "compute_pwm", "get_haptic_intensity"):
            if hasattr(haptic_map, fn_name):
                return int(getattr(haptic_map, fn_name)(dist_m))

    if not np.isfinite(dist_m) or dist_m > max_alert_m:
        return 0
    if dist_m <= min_alert_m:
        return 100
    ratio = (max_alert_m - dist_m) / (max_alert_m - min_alert_m)
    return int(np.clip(round(ratio * 100), 0, 100))


def pwm_bar(pwm: int, width: int = 10) -> str:
    """Renders an ASCII progress bar for terminal debugging over SSH."""
    filled = int(round((pwm / 100.0) * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + f"] {pwm:3d}%"


def run_system(cam_height_m: float = 1.35, mock: bool = False):
    pipeline = ZoneDepthPipeline(
        width=640,
        height=480,
        cam_height_m=cam_height_m,
        floor_clearance_m=0.10,
        min_fill_ratio=0.08,
        confirm_frames=3,
    )

    if mock:
        print("Running full-system integration in MOCK mode (Ctrl+C to quit)...\n")
        scenarios = [
            ("Open Hallway (Floor Only)", 0.0, None),
            ("Tilted Down 20 deg at Floor", 20.0, None),
            ("Hand in Ego-Pocket (0.35m) + Cane Shaft (0.9m)", 5.0, "hand_and_cane"),
            ("Approaching Wall on Left (1.10m)", 0.0, "wall_left"),
            ("Close Wall Ahead (0.55m)", 0.0, "wall_center"),
        ]
        try:
            for label, pitch, kind in scenarios:
                print(f"\n--- Scenario: {label} (Pitch: {pitch:+.1f} deg) ---")
                frame = np.zeros((480, 640), dtype=np.float32)
                # Base floor in lower frame
                for v in range(260, 480):
                    frame[v, :] = 1.35 / max(0.05, pipeline.depth_filter.v_norm[v, 0])

                if kind == "hand_and_cane":
                    frame[350:420, 280:360] = 0.35  # Ego hand
                    frame[220:460, 317:323] = 0.90  # 6px cane shaft
                elif kind == "wall_left":
                    frame[:, :210] = 1.10
                elif kind == "wall_center":
                    frame[:, 213:426] = 0.55

                for f_idx in range(1, 4):
                    _, _, confirmed = pipeline.process_frame(frame, pitch_deg=pitch)
                    pwms = {z: dist_to_pwm(d) for z, d in confirmed.items()}
                    print(
                        f"  Frame {f_idx} | "
                        f"L: {confirmed['left']:4.2f}m {pwm_bar(pwms['left'])} | "
                        f"C: {confirmed['center']:4.2f}m {pwm_bar(pwms['center'])} | "
                        f"R: {confirmed['right']:4.2f}m {pwm_bar(pwms['right'])}"
                    )
                    time.sleep(0.15)
        except KeyboardInterrupt:
            pass
        return

    # Live RealSense D435i Mode
    import pyrealsense2 as rs

    rs_pipe = rs.pipeline()
    cfg = rs.config()
    cfg.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    cfg.enable_stream(rs.stream.accel, rs.format.motion_xyz32f, 200)

    profile = rs_pipe.start(cfg)
    depth_scale = profile.get_device().first_depth_sensor().get_depth_scale()
    intr = profile.get_stream(rs.stream.depth).as_video_stream_profile().get_intrinsics()

    pipeline.depth_filter = pipeline.depth_filter.__class__(
        width=intr.width,
        height=intr.height,
        fy=intr.fy,
        cy=intr.ppy,
        cam_height_m=cam_height_m,
    )

    print("Project Daredevil Live Loop Running! Press Ctrl+C to stop.\n")
    pitch_deg = 0.0

    try:
        while True:
            frames = rs_pipe.wait_for_frames()
            depth_frame = frames.get_depth_frame()
            if not depth_frame:
                continue

            accel_frame = frames.first_or_default(rs.stream.accel)
            if accel_frame:
                a = accel_frame.as_motion_frame().get_motion_data()
                pitch_deg = float(np.rad2deg(np.arctan2(-a.z, np.hypot(a.x, a.y))))

            depth_m = np.asanyarray(depth_frame.get_data(), dtype=np.float32) * depth_scale
            _, _, confirmed = pipeline.process_frame(depth_m, pitch_deg=pitch_deg)
            pwms = {z: dist_to_pwm(d) for z, d in confirmed.items()}

            print(
                f"\rPitch:{pitch_deg:+5.1f}° | "
                f"L:{confirmed['left']:4.2f}m {pwm_bar(pwms['left'])} | "
                f"C:{confirmed['center']:4.2f}m {pwm_bar(pwms['center'])} | "
                f"R:{confirmed['right']:4.2f}m {pwm_bar(pwms['right'])}",
                end="",
                flush=True,
            )
    except KeyboardInterrupt:
        print("\nShutting down Project Daredevil.")
    finally:
        rs_pipe.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Run 5 simulated scenarios without D435i")
    parser.add_argument("--cam-height", type=float, default=1.35, help="Camera height in meters")
    args = parser.parse_args()
    run_system(cam_height_m=args.cam_height, mock=args.mock)