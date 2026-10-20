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