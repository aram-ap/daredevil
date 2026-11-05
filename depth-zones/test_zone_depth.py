"""Tests for zone_depth.py using synthetic depth frames (no camera needed).

Synthetic scene: 640x480 depth stream, fy=385, cy=240, camera 1.2 m high, pitched
down 0.15 rad. The floor is generated from the SAME geometric model the code
uses, so these tests check the logic (masking, zones, history filter), not
whether the model matches a real D435i -- that needs the Jetson.
"""
import numpy as np
import pytest

import zone_depth as zd

H, W = 480, 640
FY, CY, CAM_H, PITCH, SCALE = 385.0, 240.0, 1.2, 0.15, 0.001
NO_OBSTACLES = {"Left": None, "Center": None, "Right": None}


def floor_frame_m():
    """Meters frame containing only floor (NaN above the horizon)."""
    exp = zd.expected_floor_depth(H, FY, CY, CAM_H, PITCH)
    return np.repeat(exp[:, None], W, axis=1).astype(np.float32)


def to_raw(depth_m):
    raw = np.zeros(depth_m.shape, np.uint16)
    ok = np.isfinite(depth_m)
    raw[ok] = np.round(depth_m[ok] / SCALE).astype(np.uint16)
    return raw


def add_box(depth_m, rows, cols, z):
    out = depth_m.copy()
    out[rows[0]:rows[1], cols[0]:cols[1]] = z
    return out


def make_detector(decimate=1, **kw):
    return zd.ZoneDetector(SCALE, FY, CY, CAM_H, decimate=decimate, **kw)


both_resolutions = pytest.mark.parametrize("decimate", [1, 2])


# ---- units -----------------------------------------------------------------
def test_to_meters_zero_is_nan_not_zero():
    raw = np.array([[0, 1000]], np.uint16)
    m = zd.to_meters(raw, 0.001)
    assert np.isnan(m[0, 0])
    assert m[0, 1] == pytest.approx(1.0)


# ---- floor model -----------------------------------------------------------
def test_floor_depth_decreases_toward_bottom_of_image():
    exp = zd.expected_floor_depth(H, FY, CY, CAM_H, PITCH)
    valid = exp[np.isfinite(exp)]
    assert np.all(np.diff(valid) < 0)          # lower rows = closer floor


def test_floor_depth_geometry_hand_check():
    # pitch 0: Z = h / v, v = (row - cy) / fy
    exp = zd.expected_floor_depth(H, FY, CY, CAM_H, 0.0)
    row = int(round(CY + 0.5 * FY))
    assert exp[row] == pytest.approx(CAM_H / ((row - CY) / FY), rel=1e-4)


def test_flat_floor_fully_masked():
    f = floor_frame_m()
    exp = zd.expected_floor_depth(H, FY, CY, CAM_H, PITCH)
    assert zd.floor_mask(f, exp)[np.isfinite(f)].all()


@both_resolutions
def test_flat_floor_gives_no_obstacles(decimate):
    det = make_detector(decimate)
    assert det.process(to_raw(floor_frame_m()), PITCH) == NO_OBSTACLES


def test_wrong_pitch_leaks_floor_as_obstacle():
    """Documents WHY pitch matters: a 0.15 rad pitch error breaks the floor mask."""
    zones = make_detector().process(to_raw(floor_frame_m()), pitch_rad=0.0)
    assert any(z is not None for z in zones.values())


# ---- zones / range window --------------------------------------------------
def test_zone_edges_match_object_detection_py():
    # object_detection.py: LEFT_ZONE_END = int(640*0.33), RIGHT_ZONE_START = int(640*0.67)
    assert zd.zone_edges(640) == [0, 211, 428, 640]


@both_resolutions
def test_center_obstacle_reported_in_center_zone_only(decimate):
    f = add_box(floor_frame_m(), (120, 300), (280, 360), 1.5)
    zones = make_detector(decimate).process(to_raw(f), PITCH)
    assert zones["Left"] is None and zones["Right"] is None
    assert zones["Center"] == pytest.approx(1.5, abs=0.02)


def test_left_and_right_obstacles_pick_correct_zones():
    f = add_box(floor_frame_m(), (120, 300), (20, 120), 1.0)
    f = add_box(f, (120, 300), (520, 620), 2.0)
    zones = make_detector().process(to_raw(f), PITCH)
    assert zones["Left"] == pytest.approx(1.0, abs=0.02)
    assert zones["Center"] is None
    assert zones["Right"] == pytest.approx(2.0, abs=0.02)


def test_zone_boundary_columns():
    frame = np.full((H, W), np.nan, np.float32)
    frame[:, :211] = 1.0                       # exactly the Left zone
    d, _ = zd.process_depth_frame(frame)
    assert d == {"Left": pytest.approx(1.0), "Center": None, "Right": None}
    frame[:, :211] = np.nan
    frame[:, 211:428] = 2.0                    # exactly the Center zone
    d, _ = zd.process_depth_frame(frame)
    assert d == {"Left": None, "Center": pytest.approx(2.0), "Right": None}


@pytest.mark.parametrize("z, expect", [(0.4, None), (0.55, 0.55), (2.9, 2.9), (3.5, None)])
def test_alert_window_is_0p5_to_3p0_m(z, expect):
    frame = np.full((H, W), np.nan, np.float32)
    frame[100:300, 280:360] = z
    d, _ = zd.process_depth_frame(frame)
    if expect is None:
        assert d["Center"] is None
    else:
        assert d["Center"] == pytest.approx(expect, abs=1e-3)


def test_process_depth_frame_accepts_zeros_like_object_detection_py():
    """object_detection.py passes raw*scale with 0 for 'no reading' (no NaN)."""
    frame = np.zeros((H, W), np.float32)
    frame[100:300, 280:360] = 1.5
    d, valid = zd.process_depth_frame(frame)
    assert d["Center"] == pytest.approx(1.5, abs=1e-3)
    assert valid.shape == frame.shape and valid.dtype == bool


def test_ignore_mask_removes_pixels():
    frame = np.full((H, W), np.nan, np.float32)
    frame[100:300, 280:360] = 1.5
    ignore = np.zeros((H, W), bool)
    ignore[:, 250:400] = True
    d, valid = zd.process_depth_frame(frame, ignore)
    assert d["Center"] is None and not valid[:, 250:400].any()


def test_single_speckle_pixel_ignored():
    f = floor_frame_m()
    f[100, 320] = 0.9                          # one bad stereo pixel
    assert make_detector().process(to_raw(f), PITCH) == NO_OBSTACLES


def test_zero_pixels_never_become_close_obstacle():
    f = add_box(floor_frame_m(), (120, 300), (280, 360), 1.5)
    f[150:160, 300:310] = np.nan               # hole in the depth data
    zones = make_detector().process(to_raw(f), PITCH)
    assert zones["Center"] == pytest.approx(1.5, abs=0.02)


# ---- dropoff (stretch / spike S4) ------------------------------------------
def test_dropoff_mask_flags_surface_below_floor_level():
    exp = zd.expected_floor_depth(H, FY, CY, CAM_H, PITCH)
    f = floor_frame_m()
    f[400:460, 200:400] += 1.0                 # floor 1 m farther than expected
    drop = zd.dropoff_mask(f, exp)
    assert drop[400:460, 200:400].all()
    assert not drop[:300].any()
    assert not zd.floor_mask(f, exp)[400:460, 200:400].any()


# ---- body filter (hands / cane) --------------------------------------------
HAND_Z = 0.7          # inside the 0.5-3 m window AND under near_max_m (0.8 m)


def hand_frames(n, rng):
    base = floor_frame_m()
    for _ in range(n):
        f = add_box(base, (400, 470), (50, 150), HAND_Z)
        f[400:470, 50:150] += rng.normal(0, 0.005, (70, 100)).astype(np.float32)
        yield f


@both_resolutions
def test_static_near_object_ignored_after_window_fills(decimate):
    rng = np.random.default_rng(0)
    det = make_detector(decimate, n_frames=10)
    results = [det.process(to_raw(f), PITCH) for f in hand_frames(12, rng)]
    assert results[0]["Left"] == pytest.approx(HAND_Z, abs=0.02)   # warm-up: still reported
    assert results[-1] == NO_OBSTACLES                              # steady state: ignored


def test_hand_that_starts_moving_is_released():
    """A near object that begins closing in must stop being ignored."""
    rng = np.random.default_rng(1)
    det = make_detector(n_frames=10, near_max_m=1.2)
    for f in hand_frames(12, rng):
        det.process(to_raw(f), PITCH)
    base = floor_frame_m()
    zones: dict = {}
    for i in range(10):                                   # now sweeps 0.7 -> 0.52 m
        zones = det.process(to_raw(add_box(base, (400, 470), (50, 150), 0.7 - 0.02 * i)), PITCH)
    assert zones["Left"] is not None


def test_approaching_near_obstacle_is_not_ignored():
    det = make_detector(n_frames=10, near_max_m=1.2)
    base = floor_frame_m()
    last: dict = {}
    for i in range(10):
        z = 1.1 - 0.05 * i                                # closing in at 0.05 m/frame
        last = det.process(to_raw(add_box(base, (120, 300), (280, 360), z)), PITCH)
    assert last["Center"] == pytest.approx(0.65, abs=0.03)


def test_far_static_object_not_treated_as_body():
    det = make_detector(n_frames=10)
    base = add_box(floor_frame_m(), (120, 300), (280, 360), 2.0)
    zones: dict = {}
    for _ in range(12):
        zones = det.process(to_raw(base), PITCH)
    assert zones["Center"] == pytest.approx(2.0, abs=0.02)   # static but beyond near_max_m


def test_ring_buffer_wraps_without_growing():
    det = make_detector(n_frames=4)
    raw = to_raw(floor_frame_m())
    for _ in range(3):
        det.process(raw, PITCH)
    assert det.body._hi is not None
    shape = det.body._hi.shape
    for _ in range(50):
        det.process(raw, PITCH)
    assert det.body._hi is not None and det.body._hi.shape == shape == (4, H, W)
