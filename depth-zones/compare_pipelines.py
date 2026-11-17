"""compare_pipelines.py -- score the two zone pipelines on one recorded depth clip.

Story/task:     ER-1-T-2 (task 8.3: tune filtering and confirmation settings)
Needs hardware: no. Reads an .npz clip made by depth-clips/clip_tools.py
Verified:       synthetic frames (tests/). UNVERIFIED(hw): behavior on real clips until run on them.

Runs both zone pipelines that are on main over the same frames and reports how steady each one is:
    ours   ZoneDetector (zone_depth.py): floor mask + hands/cane history filter + percentile zones
    kaleb  ZoneDepthPipeline (backup_zone_depth.py): 3D floor/ego-pocket filter + 3-frame confirmation
Kaleb's pipeline is scored as it ships, with its confirmation, so its first two frames are always
clear. Both series go through the same HapticMapper for the motor-vector numbers.

    python compare_pipelines.py ../depth-clips/clips/x.npz --cam-height-m 1.2 [--pitch-deg 0]

It does not change or tune either pipeline and does not say which one is better.
"""
from __future__ import annotations

import argparse
import math
from typing import Dict, List, Optional, Sequence

import numpy as np

from backup_zone_depth import ZoneDepthPipeline
from haptic_map import HapticMapper
from zone_depth import ZONE_NAMES, ZoneDetector

Zones = Dict[str, Optional[float]]
KALEB_KEYS = ("left", "center", "right")      # ZoneDepthPipeline's zone names, in ZONE_NAMES order


def run_clip(frames: Sequence[np.ndarray], depth_scale: float, fy: float, cy: float,
             cam_height_m: float, pitch_deg: float = 0.0) -> Dict[str, List[Zones]]:
    """Run both pipelines over raw uint16 depth frames. Returns {"ours": series, "kaleb": series}.

    Each series has one {"Left","Center","Right"} dict per frame: meters, or None for clear.
    """
    first = np.asarray(frames[0])
    height, width = first.shape
    ours = ZoneDetector(depth_scale, fy, cy, cam_height_m)
    kaleb = ZoneDepthPipeline(width=width, height=height, fy=fy, cy=cy, cam_height_m=cam_height_m)
    pitch_rad = math.radians(pitch_deg)
    out: Dict[str, List[Zones]] = {"ours": [], "kaleb": []}
    for raw in frames:
        raw = np.asarray(raw)
        out["ours"].append(ours.process(raw, pitch_rad))
        depth_m = raw.astype(np.float32) * np.float32(depth_scale)
        _, _, confirmed = kaleb.process_frame(depth_m, pitch_deg=pitch_deg)
        out["kaleb"].append({
            name: (float(confirmed[key]) if np.isfinite(confirmed[key]) else None)
            for name, key in zip(ZONE_NAMES, KALEB_KEYS)
        })
    return out


def score(series: Sequence[Zones], fps: float = 30.0) -> dict:
    """Steadiness numbers for one pipeline's series (see the task file for the definitions)."""
    n = len(series)
    secs = n / fps if n else 0.0
    zones = {}
    for name in ZONE_NAMES:
        vals = [frame[name] for frame in series]
        clear = sum(v is None for v in vals)
        flips = sum((vals[i] is None) != (vals[i - 1] is None) for i in range(1, n))
        zones[name] = {"clear_pct": 100.0 * clear / n if n else 0.0,
                       "flips_per_s": flips / secs if secs else 0.0}
    mapper = HapticMapper()                       # fresh state, so hysteresis starts clean
    vectors = []
    for frame in series:
        m = mapper.map(frame)
        vectors.append(m["left"] + m["right"])
    steps = max(n - 1, 0)
    changed = sum(vectors[i] != vectors[i - 1] for i in range(1, n))
    return {"frames": n, "zones": zones,
            "motor_changed_pct": 100.0 * changed / steps if steps else 0.0}


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Score both zone pipelines on one recorded clip.")
    p.add_argument("npz", help="clip exported by depth-clips/clip_tools.py")
    p.add_argument("--cam-height-m", type=float, required=True, help="camera height above the floor")
    p.add_argument("--pitch-deg", type=float, default=0.0, help="fixed camera pitch below horizontal")
    p.add_argument("--fps", type=float, default=30.0)
    args = p.parse_args(argv)

    with np.load(args.npz) as z:
        frames, scale, fy, cy = z["depth"], float(z["depth_scale"]), float(z["fy"]), float(z["ppy"])
    results = run_clip(frames, scale, fy, cy, args.cam_height_m, args.pitch_deg)
    for name in ("ours", "kaleb"):
        s = score(results[name], args.fps)
        print(f"\n{name}  ({s['frames']} frames)")
        for zone in ZONE_NAMES:
            z = s["zones"][zone]
            print(f"  {zone:6s} clear {z['clear_pct']:5.1f}%   flips/s {z['flips_per_s']:5.1f}")
        print(f"  motor vector changed on {s['motor_changed_pct']:.0f}% of frame steps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
