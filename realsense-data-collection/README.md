# RealSense Depth Data Collection (Project Daredevil)

Script for collecting and verifying depth measurements from the Intel RealSense
D435i on the Jetson Orin Nano. Owner: Chad.

## Purpose
Capture depth data and check how accurate it is against physically measured
truth, so the object detection and haptic feedback work builds on known numbers.
This is a camera accuracy tool. It is not the obstacle-detection pipeline.

## Status
- [x] Multi-frame capture at a known distance: mean, median, std, error vs tape
- [x] Command-line options (`--distance`, `--frames`, `--out`)
- [x] CSV output, one row appended per trial
- [x] pytest tests for the math and CSV code (9 tests, no camera needed)
- [ ] Run on the Jetson with the D435i and fill in the results table below
- [ ] Record to .bag (not implemented)
- [ ] Depth heatmap visualization (not implemented)

## Hardware / Software
- Intel RealSense D435i, Jetson Orin Nano
- Python 3, NumPy, pyrealsense2 (Jetson: TODO document build steps)
- pytest for the tests. matplotlib is listed in requirements.txt for the planned
  heatmap; nothing uses it yet.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```
pyrealsense2 is installed separately (the Jetson needs a special build). The
tests do not need it or a camera; `collect_depth.py` needs both.

Run the tests from this folder:
```bash
python -m pytest
```

## Usage
Run from this folder (the default output path is relative to where you run it):
```bash
python collect_depth.py --distance 1.0
python collect_depth.py --distance 2.0 --frames 300 --out data/results.csv
```

| Option | Required | Default | Meaning |
| --- | --- | --- | --- |
| `--distance` | yes | | Tape-measured distance from the camera to the target, in meters |
| `--frames` | no | 200 | Frames to capture after warm-up |
| `--out` | no | `data/results.csv` | CSV file to append to. Created with a header row if it doesn't exist. The folder must already exist (`data/` does) |

What a run does:
1. Starts a 640x480, 30 fps depth stream.
2. Discards 30 warm-up frames (about 1 s) so auto-exposure can settle.
3. Captures `--frames` frames, reducing each to one median distance from a patch at
   the image center.
4. Prints one summary line, for example (format only, numbers are made up):
   `Mean: 1.0023 m  Std: 0.0031 m  Error vs tape: +2.3 mm  Valid: 98%`
5. Appends the trial to the CSV.

If no frame has a valid reading, it prints "No valid depth readings..." and
writes nothing. The camera is released even if the run is interrupted.

### CSV columns
| Column | Meaning |
| --- | --- |
| `true_distance_m` | The `--distance` you typed (tape measure) |
| `n_frames_total` | Frames captured |
| `n_frames_valid` | Frames that had a usable center-patch reading |
| `mean_m`, `median_m` | Average and median of the per-frame distances |
| `std_m` | Spread of the readings: how noisy (repeatability) |
| `error_m` | `mean_m - true_distance_m`: positive means the camera reads too far (accuracy) |
| `mean_valid_fraction` | Average fraction of valid pixels in the patch, over all frames |

## How it works
- The camera gives a depth frame: a 640x480 grid of 16-bit integers (z16).
- Meters = raw value x depth scale (read from the camera; ~0.001).
- A raw value of 0 means "no reading", not 0 m, so zeros are excluded.
- We summarize a small center patch (21x21 pixels, median) instead of one noisy pixel.

## Verification method
Fix the camera, place a flat object (cardboard) square to it and centered in the
frame, at tape measured distances. Capture many frames per distance and compare
the readings to the tape measurement. Measure from the same point on the camera
every time and note which point you used. Sprint 1 task 1.5 uses 0.5, 1, 2 and 3 m;
the OI-1 target is within 10 cm over that range.

| True distance | Mean | Median | Std | Error | Valid |
| --- | --- | --- | --- | --- | --- |
| 0.5 m | TODO | TODO | TODO | TODO | TODO |
| 1.0 m | TODO | TODO | TODO | TODO | TODO |
| 2.0 m | TODO | TODO | TODO | TODO | TODO |
| 3.0 m | TODO | TODO | TODO | TODO | TODO |

## Limitations
- Only the image-center patch is measured: no off-center accuracy, no zones.
- Static targets only; moving-object behaviour is not tested.
- Not verified on the Jetson yet (see Status).

## Open questions
- Does pyrealsense2 install cleanly on the Jetson?
- Output format for the object-detection code: for now
  `object-detection/object_detection.py` reads depth frames directly and does not
  use this CSV, so this tool stays an accuracy check.

## References
- librealsense: https://github.com/IntelRealSense/librealsense
- Python example: wrappers/python/examples/python-tutorial-1-depth.py
