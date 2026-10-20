import numpy as np
import pytest

from depth_math import depth_to_meters, center_patch_stats

DEPTH_SCALE = 0.001  # 1 raw unit = 1 mm


def make_image_with_center_patch(value):
    """480x640 image of zeros with the 21x21 center patch set to `value`."""
    image = np.zeros((480, 640), dtype=np.uint16)
    image[230:251, 310:331] = value
    return image


def test_depth_to_meters_converts_units():
    assert depth_to_meters(1000, DEPTH_SCALE) == pytest.approx(1.0)


def test_all_valid_patch():
    image = make_image_with_center_patch(1500)
    median_m, valid_frac = center_patch_stats(image, DEPTH_SCALE)
    assert median_m == pytest.approx(1.5)
    assert valid_frac == pytest.approx(1.0)


def test_all_zero_patch_returns_no_reading():
    image = np.zeros((480, 640), dtype=np.uint16)
    median_m, valid_frac = center_patch_stats(image, DEPTH_SCALE)
    assert median_m is None
    assert valid_frac == 0.0


def test_zeros_are_excluded_from_median():
    image = make_image_with_center_patch(2000)
    image[230:245, :] = 0            # top 15 of 21 rows have no reading
    median_m, valid_frac = center_patch_stats(image, DEPTH_SCALE)
    assert median_m == pytest.approx(2.0)   # would be 0.0 if zeros were counted
    assert valid_frac == pytest.approx(6 / 21)