"""clip_tools.py -- read recorded clips: summarize, replay, and export to .npz.

Story/task:     task I6; lets zone/floor/cane code (depth-zones/) run with no camera attached
Needs hardware: no. Reading a .bag needs pyrealsense2 (no camera); reading a .npz needs only numpy
Verified:       the .npz save/load round trip on synthetic frames. UNVERIFIED(hw): reading a real
                .bag (end-of-file handling, IMU alignment) until the first real clip is replayed.

Both sources yield the same thing, so downstream code does not care which one it gets:
    for t_ms, depth_raw, accel in iter_bag("clips/x.bag"):    # or iter_npz("clips/x.npz")
        depth_raw: uint16 array (h, w), raw units (multiply by depth_scale for meters; 0 = no reading)
        accel:     (ax, ay, az) latest accelerometer sample, or None if the clip has no IMU

Use the .npz for remote work: it needs no SDK, so any laptop can open it. Export once where
pyrealsense2 is installed:   python3 clip_tools.py export clips/x.bag

Command line:
    python3 clip_tools.py info   clips/x.bag
    python3 clip_tools.py export clips/x.bag [--out clips/x.npz] [--max-frames 600]
    python3 clip_tools.py video  clips/x.npz [--out clips/x.mp4]   # heatmap video any player opens
        the video also prints, per zone, the 5th-percentile distance (p5), the distance of the
        N-th nearest valid pixel (N300 by default, set with --nth) and the valid-pixel count
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np

Accel = Optional[Tuple[float, float, float]]
Sample = Tuple[float, np.ndarray, Accel]


def _open_bag(path: str):
    """Start a replay pipeline on a .bag. Returns (pipeline, profile, rs module)."""
    import pyrealsense2 as rs   # imported here so .npz files work without the SDK

    if not Path(path).is_file():
        raise SystemExit(f"No such file: {path}")
    cfg = rs.config()
    cfg.enable_device_from_file(path, repeat_playback=False)
    pipeline = rs.pipeline()
    profile = pipeline.start(cfg)
    # Not real-time: hand frames over as fast as we consume them, none skipped.
    profile.get_device().as_playback().set_real_time(False)
    return pipeline, profile, rs


def bag_meta(path: str) -> Dict[str, float]:
    """Depth scale and intrinsics stored in the bag (needed to turn raw units into meters)."""
    pipeline, profile, rs = _open_bag(path)
    try:
        intr = profile.get_stream(rs.stream.depth).as_video_stream_profile().get_intrinsics()
        return {"depth_scale": profile.get_device().first_depth_sensor().get_depth_scale(),
                "fx": intr.fx, "fy": intr.fy, "ppx": intr.ppx, "ppy": intr.ppy}
    finally:
        pipeline.stop()


def iter_bag(path: str) -> Iterator[Sample]:
    """Yield (timestamp_ms, depth_raw, latest_accel) for each depth frame in the bag."""
    pipeline, _profile, rs = _open_bag(path)
    last_accel: Accel = None
    try:
        while True:
            try:
                fs = pipeline.wait_for_frames(2000)
            except RuntimeError:
                break   # playback has run out of frames
            accel = fs.first_or_default(rs.stream.accel)
            if accel:
                d = accel.as_motion_frame().get_motion_data()
                last_accel = (d.x, d.y, d.z)
            depth = fs.get_depth_frame()
            if depth:
                yield depth.get_timestamp(), np.asanyarray(depth.get_data()).copy(), last_accel
    finally:
        pipeline.stop()


def export_npz(bag_path: str, out_path: str, max_frames: int = 0) -> int:
    """Read every depth frame of a bag and save one compressed .npz. Returns the frame count.

    Everything is held in memory first: ~0.6 MB per 640x480 frame, so 600 frames (20 s at
    30 fps) is ~370 MB. Use --max-frames for long clips.
    """
    meta = bag_meta(bag_path)
    ts: List[float] = []
    frames: List[np.ndarray] = []
    accels: List[Tuple[float, float, float]] = []
    for t, depth, accel in iter_bag(bag_path):
        ts.append(t)
        frames.append(depth)
        accels.append(accel if accel is not None else (np.nan, np.nan, np.nan))
        if max_frames and len(frames) >= max_frames:
            break
    if not frames:
        raise SystemExit("No depth frames found in that file.")
    save_npz(out_path, np.stack(frames), np.array(ts), np.array(accels, np.float32), meta)
    return len(frames)


def save_npz(out_path: str, depth: np.ndarray, t_ms: np.ndarray, accel: np.ndarray,
             meta: Dict[str, float]) -> None:
    """Write the arrays plus calibration. accel rows are NaN where the clip had no IMU sample."""
    np.savez_compressed(out_path, depth=depth.astype(np.uint16), t_ms=t_ms.astype(np.float64),
                        accel=accel.astype(np.float32), **{k: np.float64(v) for k, v in meta.items()})


def load_npz(path: str) -> Dict[str, np.ndarray]:
    """Load an exported clip: keys depth (N,h,w) uint16, t_ms, accel (N,3), depth_scale, fx, fy, ppx, ppy."""
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def iter_npz(path: str) -> Iterator[Sample]:
    """Same output as iter_bag, from an exported .npz (no SDK needed)."""
    z = load_npz(path)
    for t, depth, a in zip(z["t_ms"], z["depth"], z["accel"]):
        yield float(t), depth, None if np.isnan(a).any() else (float(a[0]), float(a[1]), float(a[2]))


ZONE_NAMES = ("Left", "Center", "Right")
ZONE_SPLITS = (0.33, 0.67)   # same split as depth-zones/zone_depth.py (and object-detection/)


def zone_readings(depth_raw: np.ndarray, depth_scale: float, *, win_min_m: float = 0.5,
                  win_max_m: float = 3.0, percentile: float = 5.0, nth: int = 300,
                  min_pixels: int = 50, speckle: bool = True) -> Dict[str, dict]:
    """Per-zone numbers for comparing zone-reduction rules on one frame. DISPLAY / analysis only.

    Valid pixel = a real reading (raw != 0) inside [win_min_m, win_max_m], optionally cleaned by the
    3x3 morphological open that depth-zones/zone_depth.py uses. For each zone returns
        {"px": valid pixels, "p": percentile distance (m) or None, "nth": N-th nearest valid pixel (m) or None}
    p is None when the zone has fewer than min_pixels valid pixels (same rule as zone_depth);
    nth is None when the zone has fewer than nth valid pixels. The floor and hands/cane filters are
    NOT applied here, so this is the zone rule alone. Defaults mirror zone_depth; nth=300 is a
    PLACEHOLDER to be tuned on clips.
    """
    import cv2

    meters = depth_raw.astype(np.float32) * depth_scale
    valid = (depth_raw > 0) & (meters >= win_min_m) & (meters <= win_max_m)
    if speckle:
        valid = cv2.morphologyEx(valid.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    w = depth_raw.shape[1]
    edges = [0, int(w * ZONE_SPLITS[0]), int(w * ZONE_SPLITS[1]), w]
    out: Dict[str, dict] = {}
    for name, a, b in zip(ZONE_NAMES, edges[:-1], edges[1:]):
        vals = meters[:, a:b][valid[:, a:b]]
        out[name] = {
            "px": int(vals.size),
            "p": float(np.percentile(vals, percentile)) if vals.size >= max(min_pixels, 1) else None,
            "nth": float(np.partition(vals, nth - 1)[nth - 1]) if 1 <= nth <= vals.size else None,
        }
    return out


def colorize(depth_raw: np.ndarray, depth_scale: float, min_m: float, max_m: float) -> np.ndarray:
    """Heatmap image (BGR) of one frame: red = near, blue = far, black = no reading.

    Fixed distance range, so a color always means the same distance (like depth-heatmap-live).
    DISPLAY only: never feed this picture to detection code.
    """
    import cv2   # imported here so the rest of this module works without OpenCV

    meters = depth_raw.astype(np.float32) * depth_scale
    scaled = np.clip((meters - min_m) / (max_m - min_m), 0.0, 1.0)
    img = cv2.applyColorMap((255 - scaled * 255).astype(np.uint8), cv2.COLORMAP_JET)
    img[depth_raw == 0] = 0
    return img


def _cmd_video(args: argparse.Namespace) -> None:
    import cv2

    if args.clip.endswith(".npz"):
        scale = float(load_npz(args.clip)["depth_scale"])
        frames = iter_npz(args.clip)
    else:
        scale = bag_meta(args.clip)["depth_scale"]
        frames = iter_bag(args.clip)
    out = args.out or str(Path(args.clip).with_suffix(".mp4"))
    writer = None
    n = 0
    t_first = None
    for t_ms, depth, _accel in frames:
        img = colorize(depth, scale, args.min_m, args.max_m)
        h, w = depth.shape
        for frac in (0.33, 0.67):   # the Left / Center / Right split depth-zones uses
            cv2.line(img, (int(w * frac), 0), (int(w * frac), h), (255, 255, 255), 1)
        t_first = t_ms if t_first is None else t_first
        centre = depth[h // 2, w // 2] * scale
        label = f"{(t_ms - t_first) / 1000:5.2f} s  frame {n}   center {centre:.2f} m" if centre > 0 \
            else f"{(t_ms - t_first) / 1000:5.2f} s  frame {n}   center: no reading"
        cv2.putText(img, label, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, label, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        zr = zone_readings(depth, scale, win_min_m=args.win_min, win_max_m=args.win_max,
                           percentile=args.percentile, nth=args.nth, min_pixels=args.min_pixels,
                           speckle=not args.no_speckle)
        zedges = [0, int(w * ZONE_SPLITS[0]), int(w * ZONE_SPLITS[1]), w]
        for name, x0 in zip(ZONE_NAMES, zedges[:-1]):
            r = zr[name]
            lines = (f"{name[0]}  p{args.percentile:g} " + (f"{r['p']:.2f} m" if r["p"] is not None else "--"),
                     f"   N{args.nth} " + (f"{r['nth']:.2f} m" if r["nth"] is not None else "--"),
                     f"   px {r['px']}")
            for k, text in enumerate(lines):
                pos = (x0 + 8, 52 + 20 * k)
                cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        if writer is None:
            writer = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (w, h))
            if not writer.isOpened():
                raise SystemExit("OpenCV could not open an mp4 writer here. Try a different --out ending (.avi).")
        writer.write(img)
        n += 1
    if writer is None:
        raise SystemExit("No depth frames found in that file.")
    writer.release()
    print(f"Wrote {out}: {n} frames at {args.fps} fps. Red = near, blue = far, black = no reading; "
          f"white lines mark the left/center/right split; text per zone = percentile, N-th nearest, valid pixels.")


def _cmd_info(args: argparse.Namespace) -> None:
    n = n_imu = 0
    t_first = t_last = 0.0
    shape = None
    for t, depth, accel in iter_bag(args.bag):
        if n == 0:
            t_first, shape = t, depth.shape
        t_last = t
        n += 1
        n_imu += accel is not None
    if n == 0:
        raise SystemExit("No depth frames found in that file.")
    meta = bag_meta(args.bag)
    dur = (t_last - t_first) / 1000.0
    print(f"{args.bag}\n  depth frames: {n}   size: {shape[1]}x{shape[0]}   duration: {dur:.1f} s"
          f"   rate: {(n - 1) / dur if dur else 0:.1f} fps")
    print(f"  IMU: {'yes' if n_imu else 'NO'}   depth_scale: {meta['depth_scale']}   "
          f"fy: {meta['fy']:.1f}   cy: {meta['ppy']:.1f}")


def _cmd_export(args: argparse.Namespace) -> None:
    out = args.out or str(Path(args.bag).with_suffix(".npz"))
    n = export_npz(args.bag, out, args.max_frames)
    print(f"Wrote {out}: {n} frames, {Path(out).stat().st_size / 1e6:.0f} MB")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("info", help="summarize a .bag")
    pi.add_argument("bag")
    pi.set_defaults(fn=_cmd_info)
    pe = sub.add_parser("export", help="convert a .bag to a compressed .npz (no SDK needed to read it)")
    pe.add_argument("bag")
    pe.add_argument("--out", default="")
    pe.add_argument("--max-frames", type=int, default=0)
    pe.set_defaults(fn=_cmd_export)
    pv = sub.add_parser("video", help="render a clip as a heatmap .mp4 you can play anywhere")
    pv.add_argument("clip", help=".npz (or .bag/.db3 where pyrealsense2 is installed)")
    pv.add_argument("--out", default="")
    pv.add_argument("--fps", type=int, default=30)
    pv.add_argument("--min-m", type=float, default=0.3, help="nearest distance mapped to a color")
    pv.add_argument("--max-m", type=float, default=4.0, help="farthest distance mapped to a color")
    pv.add_argument("--win-min", type=float, default=0.5, help="zone readings: nearest valid distance (m)")
    pv.add_argument("--win-max", type=float, default=3.0, help="zone readings: farthest valid distance (m)")
    pv.add_argument("--percentile", type=float, default=5.0, help="zone readings: percentile shown as pN")
    pv.add_argument("--nth", type=int, default=300, help="zone readings: N for the N-th nearest valid pixel")
    pv.add_argument("--min-pixels", type=int, default=50, help="zone readings: fewer valid pixels -> no percentile")
    pv.add_argument("--no-speckle", action="store_true", help="zone readings: skip the 3x3 open")
    pv.set_defaults(fn=_cmd_video)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
