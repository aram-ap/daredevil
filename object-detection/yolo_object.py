"""
Project Daredevil - YOLO Object Detection + Depth Pipeline
Target Platform : NVIDIA Jetson Orin Nano + Intel RealSense D435i
Dependencies    : pyrealsense2, opencv-python, numpy, ultralytics, sqlite3, flask

Live view: color camera feed with YOLOv8 bounding boxes and per-box
depth readings drawn directly on the frame. Zone-based haptic motor
logic (Left / Center / Right) is preserved and computed from the
nearest detected object in each zone.
"""

from database_logger import init_db, log_yolo_event
from flask import Flask, Response
import threading
import time
import numpy as np
import cv2


app = Flask(__name__)
latest_frame = None
frame_lock = threading.Lock()

def generate_mjpeg():
    global latest_frame
    while True:
        with frame_lock:
            if latest_frame is None:
                frame_bytes = None
            else:
                # Encode frame as JPEG (quality 80 balances speed & clarity)
                ret, buffer = cv2.imencode('.jpg', latest_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                frame_bytes = buffer.tobytes() if ret else None

        if frame_bytes is None:
            time.sleep(0.01)
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.03)  # Cap stream push to ~30 FPS

@app.route('/')
def video_feed():
    return Response(generate_mjpeg(), mimetype='multipart/x-mixed-replace; boundary=frame')

def start_web_server(port=8080):
    # Run Flask in a daemon thread so it exits automatically when the main script stops
    server_thread = threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False),
        daemon=True
    )
    server_thread.start()

try:
    import pyrealsense2 as rs
    REALSENSE_AVAILABLE = True
except ImportError:
    REALSENSE_AVAILABLE = False
    print("[WARN] pyrealsense2 not found — running in demo mode (webcam + no depth).")

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("[WARN] ultralytics not found — install with: pip install ultralytics")


# =============================================================================
# Configuration & Constants
# =============================================================================

FRAME_WIDTH  = 640
FRAME_HEIGHT = 480
FPS          = 30
WEB_PORT     = 8080

# YOLO model weights: 'yolov8n.pt' (nano/fastest) → 'yolov8s/m/l/x.pt' for more accuracy
YOLO_MODEL_WEIGHTS = "yolov8n.pt"

# Confidence threshold for YOLO detections
CONF_THRESHOLD = 0.40

# Depth range of interest (meters)
MIN_DIST_M = 0.3
MAX_DIST_M = 3.0

# Zone boundaries (same split as the original pipeline)
LEFT_ZONE_END    = int(FRAME_WIDTH * 0.33)
RIGHT_ZONE_START = int(FRAME_WIDTH * 0.67)

# Mask bottom 15 % to ignore floor / cane reflections
CROP_BOTTOM_PERCENT = 0.15
CROP_Y_END          = int(FRAME_HEIGHT * (1.0 - CROP_BOTTOM_PERCENT))

# How many depth pixels to sample inside a bounding box (patch half-size)
# A 20×20 patch centred on the box centre gives a robust median estimate.
DEPTH_PATCH_HALF = 10

# Colour scheme for bounding boxes per zone
ZONE_COLORS = {
    "Left":   (255, 100,   0),   # blue-orange
    "Center": (  0, 220,  60),   # green
    "Right":  (  0, 100, 255),   # red-orange
}
DEFAULT_BOX_COLOR = (200, 200, 200)


# =============================================================================
# Helpers
# =============================================================================

def get_zone(cx: int) -> str:
    """Return 'Left', 'Center', or 'Right' based on the x-coordinate."""
    if cx < LEFT_ZONE_END:
        return "Left"
    elif cx < RIGHT_ZONE_START:
        return "Center"
    else:
        return "Right"


def sample_depth_at_box(depth_m: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> float | None:
    """
    Return the median valid depth (m) inside the bounding box, or None if no
    valid pixels exist. Uses the centre patch rather than the whole box to
    reduce edge-noise near object boundaries.
    """
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2

    py1 = max(0,            cy - DEPTH_PATCH_HALF)
    py2 = min(FRAME_HEIGHT, cy + DEPTH_PATCH_HALF)
    px1 = max(0,            cx - DEPTH_PATCH_HALF)
    px2 = min(FRAME_WIDTH,  cx + DEPTH_PATCH_HALF)

    patch = depth_m[py1:py2, px1:px2]
    valid = patch[(patch >= MIN_DIST_M) & (patch <= MAX_DIST_M)]

    return float(np.median(valid)) if valid.size > 0 else None


def calculate_vibration_intensity(distance_m: float | None) -> int:
    """Scale distance (0.3–3 m) → PWM value (50–255). Closer = stronger."""
    if distance_m is None:
        return 0
    norm = (MAX_DIST_M - distance_m) / (MAX_DIST_M - MIN_DIST_M)
    return int(np.clip(norm * 205 + 50, 0, 255))


def draw_overlay(
    frame:       np.ndarray,
    detections:  list[dict],
    zone_motors: dict[str, int],
) -> np.ndarray:
    """
    Draw:
      • Vertical zone dividers + floor crop line
      • Semitransparent zone labels with motor PWM
      • Coloured bounding boxes with label + depth
    Returns the annotated frame.
    """
    overlay = frame.copy()

    # --- Zone dividers ---
    cv2.line(overlay, (LEFT_ZONE_END,    0), (LEFT_ZONE_END,    FRAME_HEIGHT), (255, 255, 255), 1)
    cv2.line(overlay, (RIGHT_ZONE_START, 0), (RIGHT_ZONE_START, FRAME_HEIGHT), (255, 255, 255), 1)
    cv2.line(overlay, (0, CROP_Y_END), (FRAME_WIDTH, CROP_Y_END), (0, 0, 200), 1)

    # --- Zone motor HUD ---
    zone_positions = {
        "Left":   (5,                    20),
        "Center": (LEFT_ZONE_END + 5,    20),
        "Right":  (RIGHT_ZONE_START + 5, 20),
    }
    for zone, (tx, ty) in zone_positions.items():
        pwm = zone_motors.get(zone, 0)
        label = f"{zone}: {pwm} PWM"
        color = ZONE_COLORS[zone]
        cv2.putText(overlay, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    # --- Bounding boxes + depth labels ---
    for det in detections:
        x1, y1, x2, y2 = det["box"]
        label         = det["label"]
        conf          = det["conf"]
        depth         = det["depth_m"]
        zone          = det["zone"]
        color         = ZONE_COLORS.get(zone, DEFAULT_BOX_COLOR)

        depth_str = f"{depth:.2f}m" if depth is not None else "no depth"
        text      = f"{label} {conf:.0%} | {depth_str}"

        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)

        # Text background pill
        (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(overlay, (x1, y1 - th - baseline - 4), (x1 + tw + 2, y1), color, -1)
        cv2.putText(overlay, text, (x1 + 1, y1 - baseline - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

    # Blend overlay for a subtle transparency on zone lines
    return cv2.addWeighted(overlay, 0.92, frame, 0.08, 0)


# =============================================================================
# Main Pipeline
# =============================================================================

def main():
    conn = init_db()
    print("=" * 60)
    print(" Project Daredevil — YOLO + Depth Vision Pipeline")
    print("=" * 60)

    # --- Load YOLO model ---
    if not YOLO_AVAILABLE:
        print("[ERROR] ultralytics is required. Install it and re-run.")
        return
    model = YOLO(YOLO_MODEL_WEIGHTS)
    print(f"[INFO]  Loaded model: {YOLO_MODEL_WEIGHTS}")

    # --- Initialise RealSense (or fall back to webcam) ---
    if REALSENSE_AVAILABLE:
        pipeline  = rs.pipeline()
        rs_config = rs.config()
        rs_config.enable_stream(rs.stream.color, FRAME_WIDTH, FRAME_HEIGHT, rs.format.bgr8, FPS)
        rs_config.enable_stream(rs.stream.depth, FRAME_WIDTH, FRAME_HEIGHT, rs.format.z16,  FPS)

        # Align depth to colour so they share the same pixel grid
        profile     = pipeline.start(rs_config)
        depth_scale = profile.get_device().first_depth_sensor().get_depth_scale()
        align       = rs.align(rs.stream.color)
        print("[INFO]  RealSense streams started (color + depth, aligned).")
    else:
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        depth_scale = None
        print("[INFO]  Using webcam — no real depth data available.")

    # --- Start Web Server ONCE before the loop ---
    start_web_server(port=WEB_PORT)
    print(f"[INFO]  Web stream live at http://<jetson-ip>:{WEB_PORT}")
    print("[INFO]  Press Ctrl+C to quit.")
    print("-" * 60)

    try:
        while True:
            # -----------------------------------------------------------------
            # 1. Grab frames
            # -----------------------------------------------------------------
            if REALSENSE_AVAILABLE:
                frames      = pipeline.wait_for_frames()
                aligned     = align.process(frames)
                color_frame = aligned.get_color_frame()
                depth_frame = aligned.get_depth_frame()

                if not color_frame or not depth_frame:
                    continue

                color_image = np.asanyarray(color_frame.get_data())
                depth_raw   = np.asanyarray(depth_frame.get_data())
                depth_m     = depth_raw * depth_scale          # shape (H, W), float64, metres
            else:
                ret, color_image = cap.read()
                if not ret:
                    break
                # Synthetic depth for demo (uniform noise)
                depth_m = np.random.uniform(0.5, 3.0, (FRAME_HEIGHT, FRAME_WIDTH))

            # -----------------------------------------------------------------
            # 2. Run YOLO inference
            # -----------------------------------------------------------------
            results = model(color_image, conf=CONF_THRESHOLD, verbose=False)[0]

            # -----------------------------------------------------------------
            # 3. Per-detection: get zone + depth
            # -----------------------------------------------------------------
            detections = []
            # Zone → list of depths for all objects in that zone
            zone_depths: dict[str, list[float]] = {"Left": [], "Center": [], "Right": []}

            for box in results.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf  = float(box.conf[0])
                cls   = int(box.cls[0])
                label = model.names[cls]
                cx    = (x1 + x2) // 2

                # Only consider detections above the floor crop line
                if y2 > CROP_Y_END and y1 > CROP_Y_END:
                    continue

                zone    = get_zone(cx)
                depth_v = sample_depth_at_box(depth_m, x1, y1, x2, y2)

                detections.append({
                    "box":     (x1, y1, x2, y2),
                    "label":   label,
                    "conf":    conf,
                    "depth_m": depth_v,
                    "zone":    zone,
                })

                if depth_v is not None:
                    zone_depths[zone].append(depth_v)

                # Log every detection to the database
                log_yolo_event(conn, label, conf, zone, depth_v)

            # -----------------------------------------------------------------
            # 4. Zone-level haptic motor commands (nearest object per zone)
            # -----------------------------------------------------------------
            zone_motors = {}
            for zone, depths in zone_depths.items():
                nearest = min(depths) if depths else None
                zone_motors[zone] = calculate_vibration_intensity(nearest)

            # -----------------------------------------------------------------
            # 5. Terminal readout
            # -----------------------------------------------------------------
            obj_summary = ", ".join(
                f"{d['label']}({d['zone']}, {d['depth_m']:.2f}m)"
                if d["depth_m"] else f"{d['label']}({d['zone']}, --)"
                for d in detections
            ) or "none"
            print(
                f"[DETECT] {obj_summary} | "
                f"Motors → L:{zone_motors.get('Left',0)} "
                f"C:{zone_motors.get('Center',0)} "
                f"R:{zone_motors.get('Right',0)}"
            )

            # -----------------------------------------------------------------
            # 6. Update Web Stream Frame
            # -----------------------------------------------------------------
            annotated_frame = draw_overlay(color_image, detections, zone_motors)

            with frame_lock:
                latest_frame = annotated_frame.copy()

    except KeyboardInterrupt:
        print("\n[INFO] Pipeline interrupted by user.")
    finally:
        if REALSENSE_AVAILABLE:
            pipeline.stop()
        else:
            cap.release()
        conn.close()
        print("[INFO] Shutdown complete.")


if __name__ == "__main__":
    main()