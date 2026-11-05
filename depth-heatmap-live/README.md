# Live Depth Heatmap over SSH (Project Daredevil)

View the RealSense D435i depth stream as a live heatmap on your laptop while the
camera is plugged into the Jetson. The Jetson serves the image; an SSH tunnel
carries it to your browser. Nothing is exposed on the network.

## Quick start (from your laptop)
```bash
cd depth-heatmap-live
./connect.sh user@jetson-ip
```
You type your SSH password once. This copies `depth_stream.py` and `launch.sh` to the Jetson
(`~/depth_heatmap_live/`), finds the project venv there that can import `pyrealsense2`, starts the
stream,
forwards port 8085, and opens http://localhost:8085 once the stream is up. Ctrl+C stops everything and
releases the camera.

Pass options after the port:
```bash
./connect.sh user@jetson-ip 8085 --scheme 6 --min-m 0.3 --max-m 2.0 --filter
```

If it picks the wrong Python, name the venv (path relative to the Jetson's home):
```bash
REMOTE_VENV=daredevil/realsense-data-collection/.venv ./connect.sh user@jetson-ip
```

## Test without the camera
```bash
python3 depth_stream.py --demo     # then open http://localhost:8085
```
Shows a synthetic moving blob, handy for checking the tunnel and browser.

## Requirements on the Jetson
- A venv with `pyrealsense2` (same one your data-collection script uses), auto-detected by `launch.sh`
- `numpy` and OpenCV. If the venv lacks `cv2`: `pip install opencv-python-headless`
- Camera on a USB 3 port; no other script holding the camera

## Options
| Flag | Default | Meaning |
|---|---|---|
| `--scheme N` | 0 | 0 Jet, 1 Classic, 2 WhiteToBlack, 3 BlackToWhite, 4 Bio, 5 Cold, 6 Warm, 7 Quantized, 8 Pattern, 9 Hue |
| `--min-m` / `--max-m` | 0.3 / 4.0 | Distance range mapped onto the colors (meters). Narrow it for more contrast at short range |
| `--filter` | off | Spatial + temporal + hole-filling filters: prettier, but smooths real data |
| `--fps`, `--width`, `--height` | 30, 640, 480 | Stream mode |
| `--quality` | 80 | JPEG quality; lower it if the tunnel is slow |
| `--port` | 8085 | Same port is used on both ends of the tunnel |

Endpoints: `/` page, `/stream` MJPEG, `/snapshot.jpg` single frame.

## Reading the picture
- Default Jet scheme: red = near, blue = far, black = no reading (raw value 0).
- The crosshair number is the raw distance at the center pixel, in meters.
- Colors use a fixed distance range (histogram equalization off), so a color
  always means the same distance from frame to frame.

## Notes
- This is a **display** step. Detection/logging should use the raw 16-bit depth,
  not the colored image or the filtered output.
- Only one process can own the camera. Stop this before running `collect_depth.py`.
- The server binds to `127.0.0.1` on the Jetson; only the SSH tunnel can reach it.

## Troubleshooting
- *`No module named 'pyrealsense2'`*: the wrong Python was used. Set `REMOTE_VENV` (see above).
- *Safari "can't connect"*: the tunnel isn't up. Read the terminal where you ran `connect.sh`; the real error is there.
- *"Could not start the camera"*: check USB 3 (`rs-enumerate-devices`), close other
  scripts using it, replug.
- *Blank page / stream (macOS)*: port 5000 is used by the AirPlay Receiver on recent macOS, so a tunnel on 5000 silently shows nothing. This tool defaults to 8085 for that reason.
- *Port already in use*: pick another, e.g. `./connect.sh user@jetson-ip 8086`.
- *Black or blank image*: point at something 0.3 m or farther; the D435i has a
  minimum range.
- *Laggy*: lower `--quality` (e.g. 50) or `--fps 15`.

## How it works
```
 Jetson                                                   Your laptop
 D435i --USB--> depth_stream.py                           browser: http://localhost:8085
                 capture thread: depth -> colorize -> JPEG        ^
                 HTTP server on 127.0.0.1:8085  --- SSH tunnel ---+
```
- Nothing listens on the network: the server binds to `127.0.0.1` and the SSH `-L` tunnel
  carries the port to your laptop. That is why no password or firewall setup is needed.
- One thread owns the camera and keeps only the newest JPEG; the web server hands that to
  every open tab. A slow connection drops frames instead of slowing the camera.
- It is MJPEG (a stream of JPEGs) on purpose: a browser plays it with a plain `<img>` tag,
  so no Flask, JavaScript or video codec is needed.

## Files
| File | Runs on | Purpose |
|---|---|---|
| `depth_stream.py` | Jetson | The streamer: camera (or `--demo`), heatmap, HTTP server |
| `connect.sh` | Laptop | One command: copies the scripts, starts the stream over SSH, opens the tunnel and your browser |
| `launch.sh` | Jetson | Finds a Python that can `import pyrealsense2` (your venv) and starts `depth_stream.py` |
| `requirements.txt` | | numpy and OpenCV; `pyrealsense2` is separate (see Requirements) |
| `.gitignore` | | Keeps `.venv/`, `__pycache__/` and `*.pyc` out of git. These are generated per machine, are large, and break on other computers |

## Building on this (slices and partitions)
Draw the zone boundaries and per-zone distances on the image in `annotate()` in
`depth_stream.py`; it already receives each frame and draws the center crosshair. Compute
zone values from the raw depth (see the comment in `capture_realsense`), then pass them in.
That gives a live view of what `depth-zones/` computes.

## Status
Camera path viewed in a browser over SSH on the Jetson (Nov 4). Not covered by automated
tests; `--demo` is the no-hardware check.
