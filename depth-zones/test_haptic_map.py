import numpy as np
import pytest

import haptic_map as hm

CLEAR = {"Left": None, "Center": None, "Right": None}


def kaleb_formula(d):
    """Copy of calculate_vibration_intensity() in object-detection/object_detection.py.
    If that version changes, update this copy and haptic_map.distance_to_intensity together."""
    if d is None:
        return 0
    norm = (3.0 - d) / (3.0 - 0.5)
    return int(np.clip(norm * 205 + 50, 0, 255))


@pytest.mark.parametrize("d", [None, 0.5, 0.8, 1.0, 1.75, 2.4, 3.0])
def test_linear_baseline_matches_object_detection_py(d):
    assert hm.distance_to_intensity(d) == kaleb_formula(d)


def test_endpoints():
    assert hm.distance_to_intensity(0.5) == 255
    assert hm.distance_to_intensity(3.0) == 50
    assert hm.distance_to_intensity(None) == 0


def assert_valid_for_set_motors(out):
    """Same checks Bracelet.set_motors() enforces in daredevil_link/bracelet.py."""
    assert set(out) == {"left", "right"}
    for vec in out.values():
        assert len(vec) == hm.NUM_MOTORS
        assert all(isinstance(v, int) and 0 <= v <= 255 for v in vec)


def test_clear_is_all_zero_and_valid():
    out = hm.HapticMapper().map(CLEAR)
    assert_valid_for_set_motors(out)
    assert out == {"left": [0, 0, 0, 0], "right": [0, 0, 0, 0]}


def test_left_zone_drives_left_outer_pair_only():
    out = hm.HapticMapper().map({**CLEAR, "Left": 1.0})
    assert_valid_for_set_motors(out)
    i = hm.distance_to_intensity(1.0)
    assert out["left"] == [i, i, 0, 0]
    assert out["right"] == [0, 0, 0, 0]


def test_right_zone_drives_right_outer_pair_only():
    out = hm.HapticMapper().map({**CLEAR, "Right": 2.0})
    i = hm.distance_to_intensity(2.0)
    assert out["right"] == [i, i, 0, 0]
    assert out["left"] == [0, 0, 0, 0]


def test_center_zone_drives_inner_pair_on_both_wrists():
    out = hm.HapticMapper().map({**CLEAR, "Center": 1.5})
    i = hm.distance_to_intensity(1.5)
    assert out["left"] == [0, 0, i, i]
    assert out["right"] == [0, 0, i, i]


def test_multiple_zones_combine_independently():
    out = hm.HapticMapper().map({"Left": 0.6, "Center": 2.5, "Right": None})
    l, c = hm.distance_to_intensity(0.6), hm.distance_to_intensity(2.5)
    assert out["left"] == [l, l, c, c]
    assert out["right"] == [0, 0, c, c]


# ---- banded mode (SF-2: >= 3 distinguishable steps) -------------------------
def test_bands_give_three_distinct_levels_across_the_window():
    m = hm.HapticMapper(bands=hm.DEFAULT_BANDS)
    levels = {m.intensity("Center", d) for d in (0.6, 1.5, 2.6)}
    assert len(levels) == 3 and 0 not in levels


def test_beyond_last_band_is_silent():
    assert hm.HapticMapper(bands=hm.DEFAULT_BANDS).intensity("Center", 3.4) == 0


def test_hysteresis_holds_band_when_receding_but_not_when_approaching():
    m = hm.HapticMapper(bands=hm.DEFAULT_BANDS, hysteresis_m=0.1)
    assert m.intensity("Center", 0.95) == 255          # nearest band
    assert m.intensity("Center", 1.05) == 255          # just past the 1.0 m edge: held
    assert m.intensity("Center", 1.2) == 160           # clearly out: drops a band
    assert m.intensity("Center", 0.95) == 255          # approaching: immediate


def test_hysteresis_is_tracked_per_zone():
    m = hm.HapticMapper(bands=hm.DEFAULT_BANDS, hysteresis_m=0.1)
    m.intensity("Left", 0.95)
    assert m.intensity("Right", 1.05) == 160           # Right has no history, no hold


def test_banded_output_valid_for_set_motors():
    out = hm.HapticMapper(bands=hm.DEFAULT_BANDS).map({"Left": 0.7, "Center": 1.5, "Right": 2.7})
    assert_valid_for_set_motors(out)
