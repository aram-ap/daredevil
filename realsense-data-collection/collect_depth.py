import argparse   # for reading command-line arguments

import numpy as np
import pyrealsense2 as rs


from depth_math import center_patch_stats, summarize_trial
from results_io import append_row_to_csv


def parse_args():
    """Define and read the options typed after the script name in the terminal."""
    # The parser object knows what options exist and reads what the user typed.
    parser = argparse.ArgumentParser(description="Measure RealSense depth at a known distance.")

    # --distance is required: the tape-measured ground truth. type=float turns the
    # typed text "1.0" into the number 1.0.
    parser.add_argument("--distance", type=float, required=True,
                        help="tape-measured distance to the target, in meters")

    # --frames is optional: if the user doesn't type it, the default (200) is used.
    parser.add_argument("--frames", type=int, default=200,
                        help="number of frames to capture (default 200)")

    # --out is optional: which CSV file the results get appended to.
    parser.add_argument("--out", default="data/results.csv",
                        help="CSV file to append results to")

    # Reads what was actually typed and returns it as an object, so later code
    # can use args.distance, args.frames, and args.out.
    return parser.parse_args()


def main():
    args = parse_args()   # read --distance / --frames / --out from the terminal

    # --- Setup: connect to the camera ---
    pipeline = rs.pipeline()   # object that owns the connection to the camera
    config = rs.config()       # describes which streams we want
    # Request depth, 640 wide x 480 tall, 16-bit integers (z16), 30 frames/sec.
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    profile = pipeline.start(config)   # submits the request; camera starts streaming

    # Read the depth scale (meters per raw integer unit) from the depth sensor.
    sensor = profile.get_device().first_depth_sensor()
    depth_scale = sensor.get_depth_scale()

    # Two lists that collect one entry per frame during the loop
    distances = []         # median distance (m), only for frames with a valid reading
    valid_fractions = []   # fraction of valid pixels in the patch, for EVERY frame

    try:
        # Warm-up: fetch and discard 30 frames (1 second at 30 fps) so the
        # camera's auto-exposure can settle
        for _ in range(30):
            pipeline.wait_for_frames()   # blocks until the next frame set arrives

        # --- Main capture loop: one pass per frame ---
        for _ in range(args.frames):
            frames = pipeline.wait_for_frames()          # bundle of frames from the camera
            depth_frame = frames.get_depth_frame()       # pull the depth frame out of the bundle
            # Wrap the frame's raw data as a NumPy array (a view, not a copy).
            # No .copy() needed: we reduce it to plain numbers below, while
            # the frame is still alive, and never store the array itself.
            depth_image = np.asanyarray(depth_frame.get_data())

            # Median distance (m) and valid-pixel fraction for the center patch.
            median_m, valid_frac = center_patch_stats(depth_image, depth_scale)
            valid_fractions.append(valid_frac)   # record this for every frame
            if median_m is not None:             # None means "no valid reading"
                distances.append(median_m)       # only keep real readings
    finally:
        # The camera is always released and
        # the next run doesn't fail with a "device busy" error.
        pipeline.stop()

    # --- After capture: compute stats over all frames ---
    result = summarize_trial(distances, valid_fractions, args.distance)
    if result is None:   # no frame had any valid reading
        print("No valid depth readings. Check the target is in front of the camera and in range.")
        return

    # Print a one-line summary. :.4f = 4 decimals, :+.1f = 1 decimal with a sign,
    # :.0% = percentage with no decimals. error_m * 1000 converts meters to mm.
    print(f"Mean: {result['mean_m']:.4f} m  Std: {result['std_m']:.4f} m  "
          f"Error vs tape: {result['error_m'] * 1000:+.1f} mm  "
          f"Valid: {result['mean_valid_fraction']:.0%}")

    append_row_to_csv(args.out, result)   # save this trial as one CSV row


# Run main() only when this file is executed directly,
# not when another file imports it.
if __name__ == "__main__":
    main()