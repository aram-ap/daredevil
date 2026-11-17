# Depth clips: record and replay RealSense .bag files (Project Daredevil)

Record full-resolution depth (plus IMU) from the D435i once, then test vision code on it any
time afterwards without the camera, without the Jetson being reachable, and as many times
as you like. This is task I6 ("record depth clips so vision code can be tested without the camera").

A `.bag` is the RealSense SDK's own recording format (newer SDKs, such as on the Jetson's Ubuntu 24.04, write `.db3` instead; the script and tools handle both). It keeps every raw 16-bit depth frame
(not a colored image), timestamps, the camera calibration, and the accelerometer/gyro.

## Record (on the machine the camera is plugged into)
```bash
cd depth-clips
python3 record_clip.py --label hallway_cane --seconds 20 --cam-height-m 1.2 --note "cane in right hand, walk to door"
```
Writes `clips/<date>_<time>_<label>.bag` (or `.db3`) and a `.json` next to it (frame counts, depth scale,
intrinsics, camera height, your note). Ctrl+C also stops it cleanly. Let it stop on its own
or with Ctrl+C: the file is only finished when the script exits.

| Option | Meaning |
|---|---|
| `--label` | Short name in the file name (what the clip is) |
| `--seconds N` | Stop after N seconds (default: until Ctrl+C) |
| `--cam-height-m` | Camera height above the floor. Needed later to replay the floor model |
| `--note` | What was in the scene, who held the cane, etc. |
| `--color` | Also record color (about 2.5x the size; only for humans, the vision code does not need it) |
| `--no-imu` | Skip accelerometer/gyro |
| `--width/--height/--fps` | Default 640x480 at 30 |

Only one process can own the camera: stop the heatmap (`depth-heatmap-live`) first.

### How big are clips?
Depth is 2 bytes per pixel: 640x480 at 30 fps is about 18 MB/s, roughly 1 GB per minute
(estimate; the script prints its own and refuses a duration that will not fit on disk). Record
short, labeled takes (10-30 s) rather than one long one.

## Use a clip
```bash
python3 clip_tools.py info   clips/<file>.bag   # or .db3          # frames, duration, fps, IMU present
python3 clip_tools.py export clips/<file>.bag          # -> clips/<file>.npz (needs no SDK to read)
```
In code, `.bag` and `.npz` give identical items, so detection code does not care which it gets:
```python
from clip_tools import iter_bag, iter_npz, load_npz

meta = load_npz("clips/x.npz")                     # depth_scale, fx, fy, ppx, ppy (cy = ppy)
for t_ms, depth_raw, accel in iter_npz("clips/x.npz"):
    ...   # depth_raw: uint16 (h, w), 0 = no reading; accel: (ax, ay, az) or None
```
Hook it to `depth-zones/` like this (`pitch_from_accel` is in `imu_pitch.py`):
```python
det = ZoneDetector(float(meta["depth_scale"]), float(meta["fy"]), float(meta["ppy"]), cam_height_m=1.2)
for t_ms, depth_raw, accel in iter_npz("clips/x.npz"):
    pitch = pitch_from_accel(*accel) if accel else 0.0
    zones = det.process(depth_raw, pitch)
```
Share clips as `.npz`: any laptop with numpy can open them. Clips are git-ignored because they
are large; copy them with `scp` or a shared drive, not git.

## Watch a clip with per-zone numbers
```bash
python3 clip_tools.py video clips/x.npz            # writes clips/x.mp4, plays in any media player
python3 clip_tools.py video clips/x.npz --nth 200 --win-min 0.3
```
Each zone shows `p5` (5th-percentile distance, what `zone_depth.py` reports today), `N300` (distance of
the 300th-nearest valid pixel, the candidate replacement) and `px` (valid pixels in the zone).
"Valid" means a real reading inside the window (`--win-min/--win-max`, default 0.5-3.0 m like
`zone_depth.py`) after the 3x3 speckle open (`--no-speckle` skips it). The floor and hands/cane
filters are not applied, so this compares the zone rule alone. The line "center 0.36 m" at the top is the
raw depth of the single middle pixel, not a zone value. N=300 is a placeholder to tune on clips.

## Recording tips for the tests we want
- Say what each clip is in `--label` and `--note`, and measure the camera height once per session.
- Useful takes: empty hallway (floor only), walking toward a wall, a chair at 1/2/3 m, cane held
  still and swinging, hands in frame, a thin pole, head tilted down and up. These are what
  `depth-zones/` thresholds (task 8.3) need.
- Record a tape-measured distance in the note when a target is static, so the clip doubles as an
  accuracy check.

## Status
- Verified on the Jetson (D435i), 2026-11-14 and 15: a 5 s smoke test and seven labeled clips recorded
  with `record_clip.py`, converted with `export`, and replayed with `video`. The newer library there
  writes `.db3` files; the script handles both `.bag` and `.db3`.
- The IMU did not stream through the library when those clips were recorded, so the script fell back
  to depth only and said so. The library was rebuilt afterwards and another script now streams the IMU;
  recording it with `record_clip.py` is not yet verified.
- Reading a `.bag` or `.db3` needs `pyrealsense2`. A `.npz` needs only NumPy and OpenCV.

### Tests
```bash
pip install -r requirements.txt
python -m pytest          # from this folder; synthetic frames, no camera, no clip files
```
Tests live in `tests/` and start with the task ID (`test_ER_1_T_1_...`).

### Smoke test
```bash
python3 record_clip.py --label smoke --seconds 5
python3 clip_tools.py info <the file it printed>      # expect ~150 frames, ~30 fps, IMU yes/NO
python3 clip_tools.py export clips/<recording>    # then open the .npz without the camera
```
