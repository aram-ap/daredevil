import numpy as np
import pyrealsense2 as rs

from depth_math import center_patch_stats


def main():
    pipeline = rs.pipeline()                  # manages the camera connection
    config = rs.config()                      # describes which streams we want
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    profile = pipeline.start(config)          # camera starts streaming

    sensor = profile.get_device().first_depth_sensor()
    depth_scale = sensor.get_depth_scale()    # meters per raw unit

    try:
        for _ in range(30):                   # let auto-exposure settle
            pipeline.wait_for_frames()

        frames = pipeline.wait_for_frames()   # one set of frames from the camera
        depth_frame = frames.get_depth_frame()
        depth_image = np.asanyarray(depth_frame.get_data())  # frame -> NumPy array

        median_m, valid_frac = center_patch_stats(depth_image, depth_scale)
        print(f"Median distance: {median_m} m, valid pixels: {valid_frac:.0%}")
    finally:
        pipeline.stop()                       # always release the camera


if __name__ == "__main__":
    main()