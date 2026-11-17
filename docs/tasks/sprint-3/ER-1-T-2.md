---
id: ER-1-T-2
story: ER-1
sprint: 3
assignee: Chad Helminiak
estimate_hours: 3
---

# Compare the two zone pipelines on one recorded depth clip

## Description
Serves ER-1 (task 8.3: tune filtering and confirmation settings). Two zone pipelines are on `main`: `ZoneDetector` in `depth-zones/zone_depth.py` and `ZoneDepthPipeline` in `depth-zones/backup_zone_depth.py`. Today nobody can say which one reads steadier or misses less on the same input. This task adds a command that runs both over one recorded `.npz` clip and prints, per pipeline and per zone, how often the zone reads clear, how often it flips between clear and obstacle, and how often the 8-motor vector would change.
Out of scope: changing or tuning either pipeline, accelerometer pitch (a fixed `--pitch-deg` is used), YOLO masking, deciding which pipeline is better, and recording or exporting clips.

## Specs
- New file `depth-zones/compare_pipelines.py`. The input is an `.npz` clip with keys `depth` (N, h, w, uint16), `depth_scale`, `fy` and `ppy`, as written by `depth-clips/clip_tools.py`.
- `compare_pipelines.run_clip(frames, depth_scale, fy, cy, cam_height_m, pitch_deg=0.0)` runs both pipelines over every frame and returns `{"ours": series, "kaleb": series}`. Each `series` is a list with one dict per frame, `{"Left": float | None, "Center": float | None, "Right": float | None}`, in meters, `None` meaning clear.
  - `"ours"` is `ZoneDetector.process`. `"kaleb"` is the confirmed zone distances from `ZoneDepthPipeline.process_frame`, so its first two frames are clear because of its 3-frame confirmation. Its `float("inf")` for no obstacle is returned as `None`, and its `left`, `center`, `right` keys are returned as `Left`, `Center`, `Right`.
- `compare_pipelines.score(series, fps=30.0)` returns `{"frames": int, "zones": {"Left": {"clear_pct": float, "flips_per_s": float}, "Center": {...}, "Right": {...}}, "motor_changed_pct": float}`.
  - `clear_pct` is the percentage of frames where the zone is `None`.
  - `flips_per_s` is the number of frame-to-frame changes between `None` and a distance, divided by the clip duration `len(series) / fps`.
  - `motor_changed_pct` is the percentage of frame steps where the 8-value vector from a fresh `HapticMapper` (`left` list then `right` list) differs from the previous frame's.
- `python depth-zones/compare_pipelines.py <clip.npz> --cam-height-m H [--pitch-deg P] [--fps F]` prints, for each of `ours` and `kaleb`, a line per zone with `clear_pct` and `flips_per_s`, and one `motor_changed_pct` line, then exits with status 0.
- Edge cases: a scene with no readings gives `None` in every zone on every frame for both pipelines; a series of one frame has no steps, so `flips_per_s` is 0 and `motor_changed_pct` is 0.

## Requirements
- No existing file changes; both pipelines are used as they are on `main`.
- Only NumPy, OpenCV and the modules already in `depth-zones/` are used. No camera and no `pyrealsense2`.
- Tests use synthetic frames only, so no clip files are needed.
- Existing tests under `depth-zones/` keep passing.

## Acceptance criteria
1. `run_clip` returns, for both pipelines, one `{"Left", "Center", "Right"}` reading per input frame, with floats in meters or `None`.
2. A static wall at 1.5 m covering the left of the frame is reported as about 1.5 m in `Left` by both pipelines, and the Center and Right zones stay `None`; the `kaleb` pipeline reports it from the third frame on.
3. A scene with no readings is reported clear (`None`) in every zone on every frame by both pipelines.
4. `score` returns the correct `clear_pct` and `flips_per_s` for a hand-built series (for example a zone alternating between 1.0 and `None`, a zone that is always a distance, and a zone that is always `None`).
5. `score` reports `motor_changed_pct` 0 for a constant series and 100 for a series that alternates between a distance and clear.
6. The command-line entry point prints a `ours` section and a `kaleb` section for a clip and returns normally.
