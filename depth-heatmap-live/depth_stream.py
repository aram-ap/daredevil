#!/usr/bin/env python3
"""
depth_stream.py -- live depth heatmap streamer for the Intel RealSense D435i.

Story/task:     visual test tool for depth work (zones, floor and cane filtering, task 8.3)
Needs hardware: yes (D435i on the Jetson); `--demo` runs without a camera
Verified:       camera path viewed in a browser over SSH to the Jetson (Chad, Nov 4);
                `--demo` checked locally

Runs ON THE JETSON. Grabs depth frames, colorizes them into a heatmap, and
serves them as an MJPEG stream over HTTP. You view it on your laptop through
an SSH port-forward (see connect.sh), so nothing is exposed on the network.

    Jetson:  python3 depth_stream.py            -> serves on 127.0.0.1:8085
    Laptop:  ssh -L 8085:localhost:8085 user@jetson   -> browse localhost:8085

No Flask needed: only pyrealsense2, numpy, and OpenCV (all already part of
the project setup). Use --demo to test without a camera.

How it is structured (worth being able to explain at standup):
  * One capture thread owns the camera and keeps the newest JPEG in memory.
  * An HTTP server hands that JPEG to any browser that asks. Slow viewers
    never slow down capture, and the camera is only opened once.
  * The heatmap is a DISPLAY step only. Raw 16-bit depth is never modified,
    so detection / logging code should keep using the raw frames.
"""
import argparse
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import cv2
except ImportError:
    raise SystemExit("OpenCV (cv2) is missing in this Python. In your venv run:\n"
                     "    pip install opencv-python-headless")
import numpy as np

# rs.colorizer color_scheme values (from librealsense)
SCHEMES = {0: "Jet", 1: "Classic", 2: "WhiteToBlack", 3: "BlackToWhite",
           4: "Bio", 5: "Cold", 6: "Warm", 7: "Quantized", 8: "Pattern", 9: "Hue"}

# The whole web page is this one string: a browser <img> pointed at /stream. The
# browser itself decodes the MJPEG stream, so no JavaScript or web framework is needed.
PAGE = b"""<!doctype html><html><head><meta charset="utf-8">
<title>Daredevil depth heatmap</title>
<style>body{margin:0;background:#111;color:#ccc;font:14px system-ui;text-align:center}
img{max-width:100%;height:auto;margin-top:8px;image-rendering:pixelated}</style></head>
<body><img src="/stream" alt="depth stream">
<p>Red = near, blue = far (Jet). Black = no reading. Number = distance at the center crosshair.</p>
</body></html>"""


class Latest:
    """Thread-safe holder for the newest JPEG so HTTP handlers can read it.

    The capture thread calls put(); each browser connection calls wait_next().
    Only the NEWEST frame is kept, so a slow viewer skips frames instead of
    building up a backlog (and never slows down the camera loop).
    """

    def __init__(self):
        self.cond = threading.Condition()
        self.jpeg = None
        self.seq = 0

    def put(self, jpeg):
        """Store a new frame and wake every browser connection waiting for one."""
        with self.cond:
            self.jpeg = jpeg
            self.seq += 1
            self.cond.notify_all()

    def wait_next(self, last_seq, timeout=5.0):
        """Block until a frame newer than last_seq exists (or timeout); return (jpeg, seq).
        Pass last_seq=-1 to get the current frame as soon as there is one."""
        with self.cond:
            self.cond.wait_for(lambda: self.seq != last_seq, timeout)
            return self.jpeg, self.seq


def annotate(img, dist_m):
    """Draw a center crosshair and the distance there (raw depth, in meters)."""
    h, w = img.shape[:2]
    cx, cy = w // 2, h // 2
    cv2.drawMarker(img, (cx, cy), (255, 255, 255), cv2.MARKER_CROSS, 20, 2)
    label = "no reading" if dist_m <= 0 else f"{dist_m:.2f} m"
    cv2.putText(img, label, (cx + 14, cy - 10), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, label, (cx + 14, cy - 10), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (255, 255, 255), 2, cv2.LINE_AA)


def capture_realsense(args, latest, stop):
    """Camera loop (runs in the worker thread): depth frame -> heatmap -> JPEG -> Latest.

    The colorizer here is only for DISPLAY. If you add detection (zones, floor
    masks), read the raw z16 values from `depth` BEFORE colorizing; do not
    threshold the colored image.
    """
    import pyrealsense2 as rs  # imported here so --demo works without it

    pipe, cfg = rs.pipeline(), rs.config()
    cfg.enable_stream(rs.stream.depth, args.width, args.height, rs.format.z16, args.fps)
    try:
        pipe.start(cfg)
    except RuntimeError as e:
        raise SystemExit(
            f"Could not start the camera: {e}\n"
            "Check: (1) camera is plugged into a USB 3 port, (2) no other script "
            "(e.g. collect_depth.py) is using it, (3) try unplugging/replugging.")

    colorizer = rs.colorizer()
    colorizer.set_option(rs.option.color_scheme, args.scheme)
    # Fixed range => colors mean the same distance every frame (no auto-stretching).
    colorizer.set_option(rs.option.histogram_equalization_enabled, 0)
    colorizer.set_option(rs.option.min_distance, args.min_m)
    colorizer.set_option(rs.option.max_distance, args.max_m)

    filters = []
    if args.filter:  # optional cleanup; makes the picture prettier, not more "true"
        filters = [rs.spatial_filter(), rs.temporal_filter(), rs.hole_filling_filter()]

    print(f"Camera started: {args.width}x{args.height}@{args.fps}, "
          f"scheme={SCHEMES.get(args.scheme, args.scheme)}, "
          f"range {args.min_m}-{args.max_m} m, filters={'on' if filters else 'off'}")
    try:
        while not stop.is_set():
            try:
                frames = pipe.wait_for_frames(5000)
            except RuntimeError:
                print("Timed out waiting for a frame; is the camera still connected?")
                continue
            depth = frames.get_depth_frame()
            if not depth:
                continue
            # Read the center distance BEFORE the filters run so the number on screen is
            # the camera's real reading, not a smoothed or hole-filled one. 0.0 means "no reading".
            dist = depth.get_distance(depth.get_width() // 2, depth.get_height() // 2)
            for f in filters:
                depth = f.process(depth)
            # .copy(): the SDK owns that buffer and reuses it; we draw on the image next.
            img = np.asanyarray(colorizer.colorize(depth).get_data()).copy()
            annotate(img, dist)
            ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
            if ok:
                latest.put(jpg.tobytes())
    finally:
        pipe.stop()


def capture_demo(args, latest, stop):
    """Fake depth (a moving blob in front of a sloped wall) to test the pipeline."""
    print("DEMO mode: synthetic depth, no camera needed")
    h, w, t = args.height, args.width, 0.0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    while not stop.is_set():
        wall = 3.0 + 0.5 * (xx / w)                         # sloped back wall, ~3 m
        bx, by = w / 2 + 150 * np.sin(t), h / 2 + 80 * np.cos(t * 0.7)
        blob = np.exp(-(((xx - bx) ** 2 + (yy - by) ** 2) / (2 * 60.0 ** 2)))
        depth_m = wall - 2.0 * blob                         # blob comes ~1 m from camera
        depth_m[:, : int(w * 0.05)] = 0                     # simulate a no-reading strip
        scaled = np.clip((depth_m - args.min_m) / (args.max_m - args.min_m), 0, 1)
        # Jet is red=near here to match the RealSense look, so invert the OpenCV map.
        img = cv2.applyColorMap((255 - scaled * 255).astype(np.uint8), cv2.COLORMAP_JET)
        img[depth_m <= 0] = 0
        annotate(img, float(depth_m[h // 2, w // 2]))
        ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
        if ok:
            latest.put(jpg.tobytes())
        t += 0.05
        time.sleep(1.0 / args.fps)


def make_handler(latest):
    """Build the HTTP request handler (a closure so it can see `latest`).

    Routes: /  the page, /stream  MJPEG (a never-ending multipart response; the
    browser swaps in each JPEG as it arrives), /snapshot.jpg  one frame.
    """
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(PAGE)))
                self.end_headers()
                self.wfile.write(PAGE)
            elif self.path.startswith("/snapshot.jpg"):
                jpg, _ = latest.wait_next(-1)
                if jpg is None:
                    self.send_error(503, "no frame yet")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpg)))
                self.end_headers()
                self.wfile.write(jpg)
            elif self.path.startswith("/stream"):
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                seq = -1
                try:
                    while True:
                        jpg, seq = latest.wait_next(seq)
                        if jpg is None:
                            continue
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                         b"Content-Length: " + str(len(jpg)).encode() +
                                         b"\r\n\r\n" + jpg + b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass  # browser tab closed
            else:
                self.send_error(404)

        def log_message(self, *a):  # keep the SSH terminal quiet
            pass
    return Handler


def main():
    """Parse options, start the capture thread, then serve HTTP until Ctrl+C.

    Threads: main = HTTP server (one extra thread per browser tab),
    worker = camera loop. They only talk through `latest`.
    """
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--port", type=int, default=8085)
    p.add_argument("--host", default="127.0.0.1",
                   help="bind address; keep 127.0.0.1 and use the SSH tunnel")
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--scheme", type=int, default=0, choices=sorted(SCHEMES),
                   help="color scheme: " + ", ".join(f"{k}={v}" for k, v in SCHEMES.items()))
    p.add_argument("--min-m", type=float, default=0.3, help="nearest distance mapped to color")
    p.add_argument("--max-m", type=float, default=4.0, help="farthest distance mapped to color")
    p.add_argument("--quality", type=int, default=80, help="JPEG quality (lower = less bandwidth)")
    p.add_argument("--filter", action="store_true", help="apply spatial/temporal/hole-fill filters")
    p.add_argument("--demo", action="store_true", help="synthetic depth, no camera")
    args = p.parse_args()

    latest, stop = Latest(), threading.Event()
    target = capture_demo if args.demo else capture_realsense
    def run_capture():
        # An uncaught error in a worker thread would otherwise vanish silently
        # (SystemExit in a thread is ignored) and leave a server with no frames.
        try:
            target(args, latest, stop)
        except BaseException as e:
            if not isinstance(e, SystemExit):
                traceback.print_exc()
            else:
                print(e, file=sys.stderr)
            print("\nCapture stopped, shutting down.", file=sys.stderr, flush=True)
            os._exit(1)

    # daemon=True so a crash in the server never leaves the process hanging on the camera thread.
    worker = threading.Thread(target=run_capture, daemon=True)
    worker.start()

    server = ThreadingHTTPServer((args.host, args.port), make_handler(latest))
    server.daemon_threads = True
    print(f"Serving on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        worker.join(timeout=3)  # lets the pipeline release the camera cleanly
        server.server_close()


if __name__ == "__main__":
    main()
