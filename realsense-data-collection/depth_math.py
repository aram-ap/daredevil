import numpy as np


def depth_to_meters(raw_value, depth_scale):
    """Convert raw depth units to meters."""
    return raw_value * depth_scale


def center_patch_stats(depth_image, depth_scale, half_size=10):
    """Median distance (m) and valid-pixel fraction of a patch at the image center."""
    h, w = depth_image.shape
    cy, cx = h // 2, w // 2
    patch = depth_image[cy - half_size : cy + half_size + 1,
                        cx - half_size : cx + half_size + 1]
    valid = patch[patch > 0]                  # 0 means "no reading"
    if valid.size == 0:
        return None, 0.0
    return depth_to_meters(np.median(valid), depth_scale), valid.size / patch.size


def summarize_trial(distances_m, valid_fractions, true_distance_m):
    """Summarize per-frame readings from one trial at a known distance.

    distances_m: one median distance per frame that had a valid reading
    valid_fractions: one valid-pixel fraction per frame (all frames)
    true_distance_m: tape-measured ground truth
    Returns a dict of stats, or None if no frame had a valid reading.
    """
    # With zero valid readings there is nothing to average, so say so explicitly
    # (the caller checks for None) instead of crashing or returning fake numbers.
    if len(distances_m) == 0:
        return None

    d = np.array(distances_m)        # turn the Python list into a NumPy array
    mean_m = float(np.mean(d))       # float() converts NumPy's number type to a plain float

    # A dict maps column names to values; the keys here become the CSV header.
    return {
        "true_distance_m": true_distance_m,
        "n_frames_total": len(valid_fractions),   # every frame captured
        "n_frames_valid": len(d),                 # frames that had a usable reading
        "mean_m": mean_m,
        "median_m": float(np.median(d)),          # median resists outlier frames
        "std_m": float(np.std(d)),                # spread: how noisy the readings are
        "error_m": mean_m - true_distance_m,      # positive = camera reads too far
        "mean_valid_fraction": float(np.mean(valid_fractions)),   # average over ALL frames
    }