"""
Project Daredevil - Depth Tracking and Zone Segmentation Pipeline
Target Platform : NVIDIA Jetson Orin Nano + Intel RealSense D435i
Dependencies: pyrealsense2, opencv-python, numpy, sqlite3
"""


import time
import sqlite3
import numpy as np
import cv2
from database_logger import init_db, log_obstacle_event


# Check if the Intel RealSense Camera is plugged in
try:
    import pyrealsense2 as rs
    ctx = rs.context()
    REALSENSE_AVAILABLE = (len(devices) > 0)
except (ImportError, Exception):
    REALSENSE_AVAILABLE = False


# =======================================================================
# Configuration & Constants
# =======================================================================


FRAME_WIDTH = 640
FRAME_HEIGHT = 480
FPS = 30

# Distance Range (From 0.5m to 3.0m)
MIN_DIST_METERS = 0.5
MAX_DIST_METERS = 3.0

# Zone Partitioning (3 Zones, Left: 33%, Center: 34%, Right: 33%)
LEFT_ZONE_END = int(FRAME_WIDTH * 0.33)
RIGHT_ZONE_START = int(FRAME_WIDTH * 0.67)

# Mask the bottom 15% of screen to prevent the floor and cane from triggering detection
CROP_BOTTOM_PERCENT = 0.15
CROP_Y_END = int(FRAME_HEIGHT * (1.0 - CROP_BOTTOM_PERCENT))

DB_NAME = "daredevil_object_log.db"


# =======================================================================
# Database Logging in SQLite 3
# =======================================================================


def init_db(db_path=DB_NAME):
    # Initialize SQLite database table for recording obstacle events
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS obstacle_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            zone TEXT NOT NULL,
            nearest_distance_m REAL NOT NULL
        )
    ''')
    conn.commit()
    return conn


def log_obstacle_event(conn, zone, distance_m):
    # Logs the timestamp, zone, and distance readings from RealSense Camera to SQLitedatabase
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO obstacle_logs (timestamp, zone, nearest_distance_m) VALUES (?, ?, ?)',
        (time.time(), zone, float(distance_m))
    )
    conn.commit()


# =======================================================================
# Depth Filtering & Zone Analysis
# =======================================================================


def process_depth_frame(depth_image_m):
    # Filters raw depth data in meters & computes nearest obstacle distances across all zones
    # Step 1 : Filter out invalid zero-depth readings & isolate 0.5 - 3.0 m range
    valid_mask = (depth_image_m >= MIN_DIST_METERS) & (depth_image_m <= MAX_DIST_METERS)
    
    # Step 2 : Exclude floor / cane from lower part of image
    valid_mask[CROP_Y_END:, :] = False
    
    # Mask non-target pixels to infinity so they're ignored in min() search
    filtered_depth = np.where(valid_mask, depth_image_m, np.inf)

    # Step 3 : Slice array into Left, Center, and Right spatial zones
    left_zone = filtered_depth[:, :LEFT_ZONE_END]
    center_zone = filtered_depth[:, LEFT_ZONE_END:RIGHT_ZONE_START]
    right_zone = filtered_depth[:, RIGHT_ZONE_START:]

    # Step 4 : Extract minimum obstacle distance per zone
    distances = {}
    for zone_name, zone_data in [('Left', left_zone), ('Center', center_zone), ('Right', right_zone)]:
        min_val = np.min(zone_data)
        distances[zone_name] = min_val if min_val != np.inf else None

    return distances, valid_mask


def calculate_vibration_intensity(distance_m):
    # Scales obstacle distance (0.5-3m) to PWM vibration strength (0-255)
    # Closer obstacles will produce a stronger vibration intensity
    if distance_m is None:
        return 0
    norm = (MAX_DIST_METERS - distance_m) / (MAX_DIST_METERS - MIN_DIST_METERS)
    return int(np.clip(norm * 205 + 50, 0, 255))


# =================================================================================
# Main Pipeline
# =================================================================================
def main():
    conn = init_db()
    print("Project Daredevil Vision Pipeline Active")
    
    if REALSENSE_AVAILABLE:
        # Initialize Intel RealSense Stream
        pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.depth, FRAME_WIDTH, FRAME_HEIGHT, rs.format.z16, FPS)
    
        profile = pipeline.start(config)
        depth_sensor = profile.get_device().first_depth_sensor()
        depth_scale = depth_sensor.get_depth_scale() # Convert mm depth to m
    else:
        print("RealSense SDK not found -- running fallback stream for testing")

    try:
        while True:
            if REALSENSE_AVAILABLE:
                frames = pipeline.wait_for_frames()
                depth_frame = frames.get_depth_frame()
                if not depth_frame:
                    continue

                # Convert frame buffer to NumPy Matrix in Meters
                depth_raw = np.asanyarray(depth_frame.get_data())
                depth_m = depth_raw * depth_scale
            else:
                depth_m = np.random.uniform(0.3, 4.0, (FRAME_HEIGHT, FRAME_WIDTH))
                time.sleep(0.1)
                
            # Analyze Frame & Extract Nearest Distances
            zone_distances, valid_mask = process_depth_frame(depth_m)

            # Calculate hapyic motor PWM values and log events
            motor_commands = {}
            for zone, distance in zone_distances.items():
                motor_commands[zone] = calculate_vibration_intensity(distance)
                if distance is not None:
                    log_obstacle_event(conn,zone,distance)

            # Terminal Output
            l_str = f"{zone_distances['Left']:.2f}m" if zone_distances['Left'] else "Clear"
            c_str = f"{zone_distances['Center']: .2f}m" if zone_distances['Center'] else "Clear"
            r_str = f"{zone_distances['Right']: .2f}m" if zone_distances['Right'] else "Clear"
            print(f"[ZONES] Left: {l_str} | Center: {c_str} | Right: {r_str} -> Motors: {motor_commands}")

            # Developer Live Visual Window
            depth_vis = (np.clip(depth_m / MAX_DIST_METERS, 0, 1) * 255).astype(np.uint8)
            depth_colormap = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)

            # Draw Zone Dividers & Floor Filter Threshold line
            cv2.line(depth_colormap, (LEFT_ZONE_END, 0), (LEFT_ZONE_END, FRAME_HEIGHT), (255,255,255),2)
            cv2.line(depth_colormap, (RIGHT_ZONE_START, 0), (RIGHT_ZONE_START, FRAME_HEIGHT), (255,255,255),2)
            cv2.line(depth_colormap, (0, CROP_Y_END), (FRAME_WIDTH, CROP_Y_END), (0,0,255), 1)
            cv2.imshow("Project Daredevil - Depth Tracking", depth_colormap)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            
    except KeyboardInterrupt:
        print("\nPipeline interrupted.")
    finally:
        if REALSENSE_AVAILABLE:
            pipeline.stop()
        conn.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
