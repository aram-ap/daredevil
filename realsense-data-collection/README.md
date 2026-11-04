# RealSense Depth Data Collection (Project Daredevil)

Script for collecting and verifying depth measurements from the Intel RealSense
D435i on the Jetson Orin Nano. Owner: Chad.

## Purpose
Capture depth data and check how accurate it is against physically measured
truth, so the object detection and haptic feedback work builds on known numbers.

## Status
- [ ] Step 1: read one frame, print center-patch distance
- [ ] Step 2: multi-frame stats vs. known distance (mean, median, std, error)
- [ ] Step 3: record to .bag, write CSV
- [ ] Step 4: pytest tests for depth_math.py
- [ ] Subtask: depth heatmap visualization

## Hardware / Software
- Intel RealSense D435i, Jetson Orin Nano
- Python 3, NumPy, pyrealsense2 (Jetson: TODO document build steps)

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Usage
TODO (fill in as the script gains arguments)

## How it works
- The camera gives a depth frame: a 640x480 grid of 16-bit integers (z16).
- Meters = raw value x depth scale (read from the camera; ~0.001).
- A raw value of 0 means "no reading", not 0 m, so zeros are excluded.
- We summarize a small center patch (median) instead of one noisy pixel.

## Verification method
Place a flat object (cardboard) at tape measured distances, capture many frames
per distance, compare the median reading to the tape measurement.
Results table: TODO

## Open questions
- What output format does the object-detection code need? (ask Kaleb)
- Does pyrealsense2 install cleanly on the Jetson?

## References
- librealsense: https://github.com/IntelRealSense/librealsense
- Python example: wrappers/python/examples/python-tutorial-1-depth.py