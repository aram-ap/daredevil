"""ER-1-T-2 tests: compare the two zone pipelines on one recorded clip.

Task file: docs/tasks/sprint-3/ER-1-T-2.md. Every test docstring starts with the task id and names
the acceptance criterion it covers. Synthetic frames only: no camera, no clip files.
"""
import numpy as np
import pytest

import compare_pipelines as cp

H, W = 480, 640
SCALE, FY, CY, CAM_H = 0.001, 384.0, 242.0, 1.2
ZONES = ("Left", "Center", "Right")


def wall_on_left(distance_m=1.5):
    raw = np.zeros((H, W), np.uint16)
    raw[:, :200] = int(distance_m / SCALE)
    return raw


def run(frames):
    return cp.run_clip(frames, SCALE, FY, CY, CAM_H)


def frame_of(left=None, center=None, right=None):
    return {"Left": left, "Center": center, "Right": right}


# ---- criterion 1 -----------------------------------------------------------------------------
def test_ER_1_T_2_run_clip_returns_one_reading_per_frame_for_both_pipelines():
    """ER-1-T-2 criterion 1: both pipelines give one Left/Center/Right dict per frame (float or None)."""
    out = run([wall_on_left()] * 4)
    assert set(out) == {"ours", "kaleb"}
    for series in out.values():
        assert len(series) == 4
        for frame in series:
            assert set(frame) == set(ZONES)
            assert all(v is None or isinstance(v, float) for v in frame.values())


# ---- criterion 2 -----------------------------------------------------------------------------
def test_ER_1_T_2_static_wall_on_the_left_is_reported_by_both_pipelines():
    """ER-1-T-2 criterion 2: a wall at 1.5 m on the left reads ~1.5 m in Left only; kaleb from frame 3."""
    out = run([wall_on_left()] * 6)
    for frame in out["ours"]:
        assert frame["Left"] == pytest.approx(1.5, abs=0.05)
        assert frame["Center"] is None and frame["Right"] is None
    kaleb = out["kaleb"]
    assert kaleb[0]["Left"] is None and kaleb[1]["Left"] is None       # 3-frame confirmation
    for frame in kaleb[2:]:
        assert frame["Left"] == pytest.approx(1.5, abs=0.05)
        assert frame["Center"] is None and frame["Right"] is None


# ---- criterion 3 -----------------------------------------------------------------------------
def test_ER_1_T_2_scene_with_no_readings_is_clear_for_both_pipelines():
    """ER-1-T-2 criterion 3: all-zero frames give None in every zone on every frame, both pipelines."""
    out = run([np.zeros((H, W), np.uint16)] * 4)
    for series in out.values():
        assert all(v is None for frame in series for v in frame.values())


# ---- criterion 4 -----------------------------------------------------------------------------
def test_ER_1_T_2_score_clear_percentage_and_flips_per_second():
    """ER-1-T-2 criterion 4: clear_pct and flips_per_s for an alternating, a constant and an empty zone."""
    series = [frame_of(2.0, 1.0, None), frame_of(2.0, None, None),
              frame_of(2.0, 1.0, None), frame_of(2.0, None, None)]
    s = cp.score(series, fps=30.0)
    assert s["frames"] == 4
    assert s["zones"]["Left"] == {"clear_pct": 0.0, "flips_per_s": 0.0}
    assert s["zones"]["Right"] == {"clear_pct": 100.0, "flips_per_s": 0.0}
    assert s["zones"]["Center"]["clear_pct"] == pytest.approx(50.0)
    assert s["zones"]["Center"]["flips_per_s"] == pytest.approx(3 / (4 / 30.0))


# ---- criterion 5 -----------------------------------------------------------------------------
def test_ER_1_T_2_motor_vector_change_is_0_for_constant_and_100_for_alternating():
    """ER-1-T-2 criterion 5: motor_changed_pct is 0 for a constant series, 100 for distance/clear toggling."""
    constant = [frame_of(1.0, 1.0, 1.0)] * 5
    assert cp.score(constant)["motor_changed_pct"] == 0.0
    alternating = [frame_of(1.0, 1.0, 1.0) if i % 2 == 0 else frame_of() for i in range(5)]
    assert cp.score(alternating)["motor_changed_pct"] == 100.0


def test_ER_1_T_2_score_of_a_single_frame_has_no_steps():
    """ER-1-T-2 criterion 5 (edge): one frame gives 0 flips per second and 0 motor changes."""
    s = cp.score([frame_of(1.0, None, None)])
    assert s["motor_changed_pct"] == 0.0
    assert all(z["flips_per_s"] == 0.0 for z in s["zones"].values())


# ---- criterion 6 -----------------------------------------------------------------------------
def test_ER_1_T_2_command_line_prints_a_section_for_each_pipeline(tmp_path, capsys):
    """ER-1-T-2 criterion 6: main() on a clip prints an ours and a kaleb section and returns 0."""
    clip = tmp_path / "c.npz"
    np.savez_compressed(clip, depth=np.stack([wall_on_left()] * 4), depth_scale=SCALE, fy=FY, ppy=CY)
    status = cp.main([str(clip), "--cam-height-m", str(CAM_H)])
    out = capsys.readouterr().out
    assert status == 0
    assert "ours" in out and "kaleb" in out
    assert out.count("Left") == 2 and "motor vector changed" in out
