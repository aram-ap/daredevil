# Shared depth clips

Recorded D435i depth clips (640x480, 30 fps, z16, depth scale 0.001) exported to
compressed `.npz`. They are too large to keep in git history (about 200 MB), so they are
published as assets on a GitHub Release instead.

**Download:** the `clips-2026-11-15` release on this repository (Releases tab), or
`gh release download clips-2026-11-15 --repo aram-ap/daredevil --dir depth-clips/clips`.
`depth-clips/clips/` is already git-ignored.

**Use:** see `README.md` for `clip_tools.py info | video | export`, and
`depth-zones/compare_pipelines.py` to run both zone pipelines on a clip.

Each `.npz` holds `depth` (N,480,640) uint16, `t_ms`, `accel` (N,3, NaN when no IMU),
`depth_scale`, `fx`, `fy`, `ppx`, `ppy`. Colour and gyro are not stored.

| Clip | Frames (about 30 fps) | Size | sha256 (first 12) | What it shows |
|---|---|---|---|---|
| 20261114_090919_smoke | 148 | 15.7 MB | 029c37d65ef5 | First smoke test, static in room |
| 20261115_121244_wall_static_1m | 179 | 15.9 MB | bbb69af137c4 | Static wall about 1 m (static near-surface case) |
| 20261115_135804_whiteboard_approach | 358 | 40.2 MB | 6e1099bd0ef9 | Whiteboard moved toward camera |
| 20261115_141215_pole_1.5m | 239 | 27.1 MB | 160ce32b9ba6 | Thin pole at about 1.5 m |
| 20261115_141502_box_floor_2m | 299 | 34.2 MB | 768fc069983f | Box on the floor at about 2 m |
| 20261115_141627_person_pass_2m | 299 | 33.8 MB | 9aedd8ab2369 | Person passing at about 2 m |
| 20261115_141746_hand_in_frame_tube | 299 | 31.6 MB | 41cb5789d605 | Hand/cane (tube) held in frame |

Each clip also has a rendered `.mp4` with per-zone overlays in the release.

Notes
- No clip has IMU samples (`accel` is all NaN), so pass `--pitch-deg` when replaying.
- Verify a download with `shasum -a 256 <file>`; the prefix should match the table.
- Distances in the names are approximate, tape-measured by hand, not ground truth.
