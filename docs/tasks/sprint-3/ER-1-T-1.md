---
id: ER-1-T-1
story: ER-1
sprint: 3
assignee: Chad Helminiak
estimate_hours: 3
---

# Replay a recorded depth clip offline and report per-zone distances

## Description
Serves ER-1 (reliable obstacle alerts between 0.5 and 3 m; tasks 8.2 and 8.3 need the same input run again and again) and the I6 card (record depth clips for testing vision code without the camera). A teammate can open a clip saved as an `.npz` on any laptop, watch what the camera saw, and get the three zone distances a rule would report, with no camera and no RealSense SDK.
Out of scope: recording from the camera (`record_clip.py` ships alongside this task, needs the hardware, and was checked by hand on the Jetson, so no criterion covers it), reading `.bag` or `.db3` files (needs the SDK), comparing the two zone pipelines against each other (a separate task), and any change to existing files in `depth-zones/`.

## Specs
- `clip_tools.save_npz(path, depth, t_ms, accel, meta)` writes a compressed `.npz`. `clip_tools.load_npz(path)` returns a dict with keys `depth` (N, h, w, uint16), `t_ms`, `accel` (N, 3), `depth_scale`, `fx`, `fy`, `ppx`, `ppy`, equal to what was saved.
- `clip_tools.iter_npz(path)` yields one `(t_ms, depth_raw, accel)` per frame, in order. `t_ms` is a float, `depth_raw` is a uint16 array (h, w), and `accel` is an `(ax, ay, az)` tuple, or `None` for a frame with no IMU sample (stored as NaN).
- `clip_tools.colorize(depth_raw, depth_scale, min_m, max_m)` returns an (h, w, 3) uint8 BGR image. Pixels with raw value 0 are black. A nearer pixel is redder than a farther one.
- `clip_tools.zone_readings(depth_raw, depth_scale, *, win_min_m=0.5, win_max_m=3.0, percentile=5.0, nth=300, min_pixels=50, speckle=True)` returns `{"Left": r, "Center": r, "Right": r}` where each `r` is `{"px": int, "p": float | None, "nth": float | None}`.
  - Zones split at columns `int(w * 0.33)` and `int(w * 0.67)`.
  - A pixel is valid when its raw value is not 0 and its distance in meters is within `[win_min_m, win_max_m]`. With `speckle=True`, a valid pixel must also survive a 3x3 morphological open, so isolated islands narrower than 3 pixels are dropped.
  - `px` is the number of valid pixels in the zone. `p` is the `percentile`-th percentile of their distances, or `None` when `px < min_pixels`. `nth` is the distance of the `nth`-nearest valid pixel, or `None` when `px < nth`.
- `python clip_tools.py video <clip.npz> [--out <file.mp4>] [--win-min M] [--win-max M] [--nth N]` writes an mp4 with exactly one frame per clip frame, drawn with `colorize`, two zone divider lines, and per-zone `p`, `N` and `px` text. The default output is the clip's name with `.mp4`.
- Edge cases: a frame with no valid pixels gives `px` 0 and `None` for both `p` and `nth`. A surface nearer than `win_min_m` is not valid until the window is widened.

## Requirements
- Reading and writing `.npz` files, `colorize` and `zone_readings` need only NumPy and OpenCV. `pyrealsense2` is imported lazily and is never needed on the `.npz` path.
- No existing file outside `depth-clips/` changes. Clip data files stay out of git (`depth-clips/.gitignore` ignores `clips/*`).
- Tests use synthetic frames, so no camera and no clip files are needed.
- Existing tests under `depth-zones/` keep passing.

## Acceptance criteria
1. A clip saved with `save_npz` and read back with `load_npz` has identical depth frames, timestamps and calibration values.
2. `iter_npz` yields frames in order as `(t_ms, depth_raw (h, w) uint16, accel)`, and `accel` is `None` for a clip recorded without an IMU.
3. `colorize` paints no-reading pixels black and makes a near pixel redder than a far pixel.
4. `zone_readings` assigns a box in the left third of the frame to `Left` only, a box in the middle to `Center` only, and a box in the right third to `Right` only.
5. For a box covering more than 5% of a zone's valid pixels, both `p` and `nth` report the box's distance.
6. For a box covering under 1% of a zone but at least `nth` pixels, `nth` reports the box's distance and `p` reports the background.
7. `p` is `None` when a zone has fewer than `min_pixels` valid pixels, `nth` is `None` when it has fewer than `nth`, and a surface nearer than `win_min_m` is excluded until the window is widened.
8. The `video` command writes an mp4 with one frame per input frame.
