"""ER-1-T-1 tests: replay a recorded depth clip offline and report per-zone distances.

Task file: docs/tasks/sprint-3/ER-1-T-1.md. Every test docstring starts with the task id and
names the acceptance criterion it covers. Synthetic frames only: no camera, no clip files.
"""
import sys

import numpy as np
import pytest

import clip_tools as ct

H, W = 480, 640          # frame size the tests use for zone_readings
SCALE = 0.001            # meters per raw unit


def make_clip(n=5, h=6, w=8, with_imu=True):
    depth = (np.arange(n * h * w).reshape(n, h, w) % 3000).astype(np.uint16)
    t = np.arange(n) * 33.3
    accel = np.tile(np.array([0.0, -9.8, 0.1], np.float32), (n, 1))
    if not with_imu:
        accel[:] = np.nan
    meta = {"depth_scale": 0.001, "fx": 385.0, "fy": 384.0, "ppx": 4.0, "ppy": 3.0}
    return depth, t, accel, meta


def wall(distance_m=2.5):
    return np.full((H, W), int(distance_m / SCALE), np.uint16)


def put_box(raw, col, size, distance_m=1.0, row=200):
    raw[row:row + size, col:col + size] = int(distance_m / SCALE)
    return raw


# ---- criterion 1 -----------------------------------------------------------------------------
def test_ER_1_T_1_round_trip_keeps_frames_timestamps_and_calibration(tmp_path):
    """ER-1-T-1 criterion 1: save_npz then load_npz gives identical frames, timestamps, calibration."""
    depth, t, accel, meta = make_clip()
    p = tmp_path / "c.npz"
    ct.save_npz(str(p), depth, t, accel, meta)
    z = ct.load_npz(str(p))
    assert z["depth"].dtype == np.uint16 and np.array_equal(z["depth"], depth)
    assert np.array_equal(z["t_ms"], t)
    for key, value in meta.items():
        assert float(z[key]) == value


# ---- criterion 2 -----------------------------------------------------------------------------
def test_ER_1_T_1_iter_npz_yields_ordered_samples(tmp_path):
    """ER-1-T-1 criterion 2: iter_npz yields (t_ms, depth (h, w) uint16, accel) in frame order."""
    depth, t, accel, meta = make_clip()
    p = tmp_path / "c.npz"
    ct.save_npz(str(p), depth, t, accel, meta)
    items = list(ct.iter_npz(str(p)))
    assert len(items) == 5
    assert [round(i[0], 1) for i in items] == [round(x, 1) for x in t]
    t0, d0, a0 = items[0]
    assert d0.shape == (6, 8) and d0.dtype == np.uint16 and np.array_equal(d0, depth[0])
    assert a0 == pytest.approx((0.0, -9.8, 0.1), abs=1e-5)


def test_ER_1_T_1_iter_npz_accel_is_none_without_imu(tmp_path):
    """ER-1-T-1 criterion 2: a clip recorded without an IMU yields accel None for every frame."""
    depth, t, accel, meta = make_clip(with_imu=False)
    p = tmp_path / "c.npz"
    ct.save_npz(str(p), depth, t, accel, meta)
    assert all(a is None for _, _, a in ct.iter_npz(str(p)))


# ---- criterion 3 -----------------------------------------------------------------------------
def test_ER_1_T_1_colorize_black_for_no_reading_and_red_for_near():
    """ER-1-T-1 criterion 3: raw 0 is black; a near pixel is redder than a far pixel."""
    pytest.importorskip("cv2")
    raw = np.array([[0, 500, 3500]], np.uint16)            # no reading, 0.5 m, 3.5 m
    img = ct.colorize(raw, SCALE, 0.3, 4.0)
    assert img.shape == (1, 3, 3) and img.dtype == np.uint8
    assert (img[0, 0] == 0).all()
    assert img[0, 1, 2] > img[0, 1, 0]                     # near: more red (index 2) than blue (0)
    assert img[0, 2, 0] > img[0, 2, 2]                     # far: more blue than red


# ---- criterion 4 -----------------------------------------------------------------------------
@pytest.mark.parametrize("zone,col", [("Left", 50), ("Center", 300), ("Right", 500)])
def test_ER_1_T_1_zone_readings_assigns_a_box_to_its_own_zone_only(zone, col):
    """ER-1-T-1 criterion 4: a 100 px box at 1.0 m changes only the zone it sits in."""
    pytest.importorskip("cv2")
    r = ct.zone_readings(put_box(wall(), col, 100), SCALE)
    for name, reading in r.items():
        expected = 1.0 if name == zone else 2.5
        assert reading["p"] == pytest.approx(expected, abs=0.01), name
        assert reading["nth"] == pytest.approx(expected, abs=0.01), name


# ---- criterion 5 and 6 -----------------------------------------------------------------------
def test_ER_1_T_1_big_box_is_reported_by_percentile_and_nth():
    """ER-1-T-1 criterion 5: a box covering ~10% of the Center zone is reported by both rules."""
    pytest.importorskip("cv2")
    c = ct.zone_readings(put_box(wall(), 300, 100), SCALE)["Center"]
    assert c["p"] == pytest.approx(1.0, abs=0.01) and c["nth"] == pytest.approx(1.0, abs=0.01)


def test_ER_1_T_1_small_box_is_reported_by_nth_but_not_percentile():
    """ER-1-T-1 criterion 6: a 30 px box (0.9% of the zone, 900 px) is seen by nth, missed by p."""
    pytest.importorskip("cv2")
    c = ct.zone_readings(put_box(wall(), 300, 30), SCALE, nth=300)["Center"]
    assert c["nth"] == pytest.approx(1.0, abs=0.01)
    assert c["p"] == pytest.approx(2.5, abs=0.01)


# ---- criterion 7 -----------------------------------------------------------------------------
def test_ER_1_T_1_none_when_zone_has_too_few_valid_pixels():
    """ER-1-T-1 criterion 7: p is None below min_pixels (50); nth is None below nth (300)."""
    pytest.importorskip("cv2")
    empty = ct.zone_readings(np.zeros((H, W), np.uint16), SCALE)
    assert all(v == {"px": 0, "p": None, "nth": None} for v in empty.values())

    tiny = put_box(np.zeros((H, W), np.uint16), 300, 5)            # 25 valid px in Center
    c = ct.zone_readings(tiny, SCALE)["Center"]
    assert c["px"] == 25 and c["p"] is None and c["nth"] is None

    medium = put_box(np.zeros((H, W), np.uint16), 300, 10)         # 100 valid px: enough for p, not nth
    c = ct.zone_readings(medium, SCALE)["Center"]
    assert c["px"] == 100 and c["p"] == pytest.approx(1.0, abs=0.01) and c["nth"] is None


def test_ER_1_T_1_surface_nearer_than_window_is_excluded_until_widened():
    """ER-1-T-1 criterion 7: a 0.4 m surface is invalid with win_min_m=0.5 and valid with 0.3."""
    pytest.importorskip("cv2")
    raw = wall(0.4)
    assert ct.zone_readings(raw, SCALE)["Center"]["px"] == 0
    widened = ct.zone_readings(raw, SCALE, win_min_m=0.3)["Center"]
    assert widened["px"] > 0 and widened["p"] == pytest.approx(0.4, abs=0.01)


# ---- criterion 8 -----------------------------------------------------------------------------
def test_ER_1_T_1_video_command_writes_one_frame_per_clip_frame(tmp_path, monkeypatch):
    """ER-1-T-1 criterion 8: `clip_tools.py video` writes an mp4 with one frame per clip frame."""
    cv2 = pytest.importorskip("cv2")
    n = 6
    depth = np.stack([wall(1.0 + 0.1 * i)[:120, :160] for i in range(n)])    # 120x160 frames
    clip = tmp_path / "c.npz"
    ct.save_npz(str(clip), depth, np.arange(n) * 33.3, np.full((n, 3), np.nan, np.float32),
                {"depth_scale": SCALE, "fx": 385.0, "fy": 385.0, "ppx": 80.0, "ppy": 60.0})
    out = tmp_path / "c.mp4"
    monkeypatch.setattr(sys, "argv", ["clip_tools.py", "video", str(clip), "--out", str(out)])
    ct.main()
    cap = cv2.VideoCapture(str(out))
    frames = 0
    while cap.read()[0]:
        frames += 1
    cap.release()
    assert frames == n
