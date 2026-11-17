"""record_clip.py -- record a RealSense .bag clip (full depth frames + IMU) for offline testing.

Story/task:     task I6 (record depth clips so vision code can be tested without the camera);
                also feeds 8.3 (tune filtering) and OA-3 (count false/missed alerts offline)
Needs hardware: yes (D435i on the Jetson or a laptop). Playback does not: see clip_tools.py
Verified:       argument handling and the size estimate only. UNVERIFIED(hw): the recording
                itself, the IMU streams on the Jetson, and the file sizes quoted in the README.

A .bag is the RealSense SDK's own recording format (newer SDKs write .db3, a ROS2-style bag; this
script uses whichever the installed SDK accepts, and clip_tools.py reads both). It keeps every raw 16-bit depth frame
(not a colored picture) plus timestamps, the camera's calibration and, if enabled, the IMU,
so the same walk can be replayed after every threshold change with no camera attached.

Typical use (on the machine the camera is plugged into):
    python3 record_clip.py --label hallway_cane --seconds 20 --cam-height-m 1.2
Ctrl+C also stops it cleanly. The bag is only valid once the pipeline has stopped, so do not
unplug the camera or kill -9 the script mid-recording.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import pyrealsense2 as rs
except ImportError:
    raise SystemExit("pyrealsense2 is missing in this Python. On the Jetson use the project venv "
                     "that can import it (see depth-heatmap-live/launch.sh for how it finds one).")

GIB = 1024 ** 3


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Record a RealSense .bag clip (depth + IMU).")
    p.add_argument("--label", default="clip",
                   help="short name used in the file name, e.g. hallway_cane (default: clip)")
    p.add_argument("--out-dir", default="clips", help="folder for the .bag and .json (default: clips)")
    p.add_argument("--seconds", type=float, default=0,
                   help="stop after this many seconds (default 0 = until Ctrl+C)")
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--color", action="store_true",
                   help="also record the color stream (about 2x the file size; helps a human "
                        "see what the scene was, the vision code does not need it)")
    p.add_argument("--no-imu", action="store_true", help="do not record accelerometer/gyro")
    p.add_argument("--cam-height-m", type=float, default=None,
                   help="camera height above the floor in meters (needed to replay the floor model)")
    p.add_argument("--pitch-deg", type=float, default=None,
                   help="camera pitch below horizontal in degrees, if known (use when the IMU is "
                        "unavailable; saved in the .json so a replay can use a fixed pitch)")
    p.add_argument("--note", default="", help="free text saved in the .json (what was in the scene)")
    return p.parse_args()


def estimate_bytes_per_second(args: argparse.Namespace) -> float:
    """Rough raw-data rate: z16 depth is 2 bytes/pixel; color (rgb8) is 3. IMU is negligible."""
    per_frame = args.width * args.height * 2
    if args.color:
        per_frame += args.width * args.height * 3
    return per_frame * args.fps


def check_disk(out_dir: Path, args: argparse.Namespace) -> None:
    """Warn before recording, not after: a full disk mid-clip corrupts the bag."""
    rate = estimate_bytes_per_second(args)
    free = shutil.disk_usage(out_dir).free
    print(f"Expect roughly {rate / 1e6:.0f} MB per second of recording "
          f"({rate * 60 / GIB:.1f} GB per minute); {free / GIB:.1f} GB free in {out_dir}/")
    if args.seconds and rate * args.seconds > free * 0.9:
        raise SystemExit("Not enough free disk space for that duration. Shorten --seconds or free space.")
    if not args.seconds and free < 5 * GIB:
        print("WARNING: under 5 GB free and no --seconds limit; watch the disk.", file=sys.stderr)


def start_recording(args: argparse.Namespace, bag_path: Path, with_imu: bool):
    """Build the stream config, point it at the .bag and start. Returns (pipeline, profile)."""
    pipeline, cfg = rs.pipeline(), rs.config()
    cfg.enable_record_to_file(str(bag_path))   # everything the pipeline streams is also written here
    cfg.enable_stream(rs.stream.depth, args.width, args.height, rs.format.z16, args.fps)
    if args.color:
        cfg.enable_stream(rs.stream.color, args.width, args.height, rs.format.rgb8, args.fps)
    if with_imu:
        # No rate given on purpose: the SDK picks a supported accel/gyro rate for this camera.
        cfg.enable_stream(rs.stream.accel, rs.format.motion_xyz32f)
        cfg.enable_stream(rs.stream.gyro, rs.format.motion_xyz32f)
    return pipeline, pipeline.start(cfg)


def open_recording(args: argparse.Namespace, base: Path, imu: bool):
    """Start recording, coping with two real-world differences. Returns (pipeline, profile, path, imu).

    1. File format: older RealSense SDKs write .bag, newer ones (found on the Jetson, Ubuntu 24.04)
       write ROS2-style .db3 and reject .bag with "Output file must have .db3 extension". Try
       .bag first, then .db3, and keep whichever the installed SDK accepts.
    2. IMU: UNVERIFIED(hw) that it streams on every setup. Only a failure that is NOT about the
       file extension triggers the depth-only fallback, so a format error is never blamed on the IMU.
    """
    for ext in (".bag", ".db3"):
        path = Path(str(base) + ext)   # not with_suffix: a "." in the label must survive
        try:
            pipeline, profile = start_recording(args, path, imu)
            return pipeline, profile, path, imu
        except (RuntimeError, TypeError) as e:
            if path.exists() and path.stat().st_size == 0:
                path.unlink()                      # a failed start can leave an empty file
            if "extension" in str(e):
                continue                           # wrong format for this SDK: try the other one
            if not imu:
                raise SystemExit(f"Could not start the camera: {e}\nCheck the USB 3 port and that no "
                                 "other script (heatmap, collect_depth.py) is using the camera.")
            print(f"WARNING: could not start with the IMU ({e}); recording DEPTH ONLY.", file=sys.stderr)
            pipeline, profile = start_recording(args, path, False)
            return pipeline, profile, path, False
    raise SystemExit("The installed RealSense SDK accepted neither a .bag nor a .db3 recording file.")


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    check_disk(out_dir, args)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = out_dir / f"{stamp}_{args.label}"
    pipeline, profile, bag_path, imu = open_recording(args, base, not args.no_imu)
    meta_path = bag_path.with_suffix(".json")

    depth_scale = profile.get_device().first_depth_sensor().get_depth_scale()
    intr = profile.get_stream(rs.stream.depth).as_video_stream_profile().get_intrinsics()
    print(f"Recording to {bag_path}  ({args.width}x{args.height}@{args.fps}, "
          f"IMU {'on' if imu else 'OFF'}, color {'on' if args.color else 'off'}). Ctrl+C to stop.")

    n_depth = n_accel = n_gyro = stalls = 0
    t0 = time.time()
    last_print = t0
    try:
        while not args.seconds or time.time() - t0 < args.seconds:
            try:
                fs = pipeline.wait_for_frames(5000)
            except RuntimeError:
                stalls += 1
                print("Timed out waiting for a frame; is the camera still connected?", file=sys.stderr)
                if stalls >= 3:
                    print("Giving up after 3 stalls; saving what was recorded.", file=sys.stderr)
                    break
                continue
            stalls = 0
            if fs.get_depth_frame():
                n_depth += 1
            if imu:
                if fs.first_or_default(rs.stream.accel):
                    n_accel += 1
                if fs.first_or_default(rs.stream.gyro):
                    n_gyro += 1
            if time.time() - last_print >= 1.0:
                last_print = time.time()
                size = bag_path.stat().st_size / 1e6 if bag_path.exists() else 0
                print(f"\r  {last_print - t0:5.1f} s   depth frames {n_depth}   "
                      f"IMU samples {n_accel}   file {size:7.0f} MB", end="", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        t_end = time.time()   # measured BEFORE stop(): finalizing the file takes a second or two
        print("\nStopping (finalizing the file) ...")
        pipeline.stop()   # this is what finishes the .bag; skipping it leaves an unreadable file

    duration = t_end - t0
    meta = {
        "label": args.label, "note": args.note,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "duration_s": round(duration, 2),
        "depth_frames": n_depth, "accel_samples": n_accel, "gyro_samples": n_gyro,
        "imu_recorded": imu and n_accel > 0,
        "width": args.width, "height": args.height, "fps": args.fps,
        "depth_scale_m_per_unit": depth_scale,
        "intrinsics": {"fx": intr.fx, "fy": intr.fy, "ppx": intr.ppx, "ppy": intr.ppy},
        "camera_height_m": args.cam_height_m,
        "fixed_pitch_deg": args.pitch_deg,
        "recording_file": bag_path.name,
        "bag_megabytes": round(bag_path.stat().st_size / 1e6, 1) if bag_path.exists() else None,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"Saved {bag_path.name}: {n_depth} depth frames in {duration:.1f} s "
          f"({n_depth / duration:.1f} fps), IMU samples {n_accel}.")
    if n_depth < 0.8 * args.fps * duration:
        print("WARNING: depth frame rate is well below the request; frames may have been dropped "
              "(slow disk or USB 2 port). Check before trusting this clip for timing.", file=sys.stderr)
    if imu and n_accel == 0:
        print("WARNING: no IMU samples were recorded; replays will have no pitch.", file=sys.stderr)
    print(f"Details: {meta_path.name}")


if __name__ == "__main__":
    main()
