import numpy as np
import pytest

from depth_math import depth_to_meters, center_patch_stats, summarize_trial

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


def test_summarize_trial_basic_stats():
    result = summarize_trial([1.0, 1.1, 0.9], [1.0, 1.0, 1.0], true_distance_m=1.0)
    assert result["mean_m"] == pytest.approx(1.0)
    assert result["median_m"] == pytest.approx(1.0)
    assert result["error_m"] == pytest.approx(0.0)
    assert result["n_frames_valid"] == 3


def test_summarize_trial_error_sign():
    result = summarize_trial([1.05, 1.05], [1.0, 1.0], true_distance_m=1.0)
    assert result["error_m"] == pytest.approx(0.05)    # reads 5 cm too far


def test_summarize_trial_counts_dropped_frames():
    # 4 frames total, but only 2 had a valid reading
    result = summarize_trial([1.0, 1.0], [1.0, 0.0, 1.0, 0.0], true_distance_m=1.0)
    assert result["n_frames_total"] == 4
    assert result["n_frames_valid"] == 2
    assert result["mean_valid_fraction"] == pytest.approx(0.5)


def test_summarize_trial_no_valid_frames_returns_none():
    assert summarize_trial([], [0.0, 0.0], true_distance_m=1.0) is None