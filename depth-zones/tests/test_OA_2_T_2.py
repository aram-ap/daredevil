"""Unit tests for Task OA-2-T-2: DirectionalZoneConfirm.

Each test function starts with `test_OA_2_T_2_` and maps directly to one of the
four numbered acceptance criteria in `docs/tasks/sprint-3/OA-2-T-2.md`.
"""
import sys
from pathlib import Path
import pytest

# Add depth-zones/ to sys.path so zone_depth can be imported directly by pytest.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "depth-zones"))

from zone_depth import DirectionalZoneConfirm


def test_OA_2_T_2_suppresses_unconfirmed_frames_until_confirm_frames_reached():
    """Criterion 1: Suppresses obstacles present for fewer than confirm_frames
    consecutive frames and outputs the confirmed distance on the confirm_frames-th frame."""
    tracker = DirectionalZoneConfirm(confirm_frames=3, clear_frames=2)

    # Frame 1 & Frame 2: left has readings, but < 3 consecutive frames -> suppressed (None).
    assert tracker.update({"left": 1.6, "center": None, "right": None})["left"] is None
    assert tracker.update({"left": 1.5, "center": None, "right": None})["left"] is None

    # Frame 3: left reaches 3 consecutive frames -> confirmed at latest distance (1.4 m).
    res = tracker.update({"left": 1.4, "center": None, "right": None})
    assert res["left"] == pytest.approx(1.4)


def test_OA_2_T_2_tracks_confirmation_independently_across_zones():
    """Criterion 2: Tracks confirmation state independently per zone so a miss in
    one zone resets only that zone's unconfirmed counter while others confirm on schedule."""
    tracker = DirectionalZoneConfirm(confirm_frames=3, clear_frames=2)

    # Frame 1: all three zones see an obstacle (streak = 1 each).
    tracker.update({"left": 1.2, "center": 2.0, "right": 0.9})

    # Frame 2: center drops out (reset to 0), while left and right reach streak = 2.
    tracker.update({"left": 1.1, "center": None, "right": 0.85})

    # Frame 3: left and right reach streak = 3 (confirmed); center is back at streak = 1 (unconfirmed).
    res = tracker.update({"left": 1.0, "center": 2.0, "right": 0.8})

    assert res["left"] == pytest.approx(1.0)
    assert res["center"] is None
    assert res["right"] == pytest.approx(0.8)


def test_OA_2_T_2_retains_confirmed_distance_across_brief_dropout_and_clears_on_clear_frames():
    """Criterion 3: Once confirmed, retains the last confirmed distance across dropouts
    shorter than clear_frames and clears to None on the clear_frames-th consecutive miss."""
    tracker = DirectionalZoneConfirm(confirm_frames=2, clear_frames=2)

    # Confirm center zone over 2 consecutive frames.
    tracker.update({"left": None, "center": 1.8, "right": None})
    assert tracker.update({"left": None, "center": 1.7, "right": None})["center"] == pytest.approx(1.7)

    # Miss 1 (1 < clear_frames=2): holds last confirmed distance of 1.7 m.
    assert tracker.update({"left": None, "center": None, "right": None})["center"] == pytest.approx(1.7)

    # Miss 2 (2 == clear_frames=2): clears to None.
    assert tracker.update({"left": None, "center": None, "right": None})["center"] is None


def test_OA_2_T_2_validates_init_params_and_resets_single_or_all_zones():
    """Criterion 4: Raises ValueError when confirm_frames < 1 or clear_frames < 1,
    and reset(zone) resets either a single valid zone or all zones while raising KeyError for unknown zones."""
    with pytest.raises(ValueError, match="confirm_frames and clear_frames must be >= 1"):
        DirectionalZoneConfirm(confirm_frames=0, clear_frames=2)

    with pytest.raises(ValueError, match="confirm_frames and clear_frames must be >= 1"):
        DirectionalZoneConfirm(confirm_frames=2, clear_frames=0)

    # Confirm all three zones (confirm_frames=2).
    tracker = DirectionalZoneConfirm(confirm_frames=2, clear_frames=2)
    tracker.update({"left": 1.0, "center": 1.5, "right": 2.0})
    tracker.update({"left": 1.0, "center": 1.5, "right": 2.0})

    # Reset only 'left' -> 'left' becomes unconfirmed on next frame while 'center' and 'right' stay confirmed.
    tracker.reset("left")
    after_single_reset = tracker.update({"left": 1.0, "center": 1.5, "right": 2.0})
    assert after_single_reset["left"] is None
    assert after_single_reset["center"] == pytest.approx(1.5)
    assert after_single_reset["right"] == pytest.approx(2.0)

    # Unknown zone name raises KeyError.
    with pytest.raises(KeyError):
        tracker.reset("up")

    # Full reset clears all zones.
    tracker.reset()
    after_full_reset = tracker.update({"left": 1.0, "center": 1.5, "right": 2.0})
    assert after_full_reset == {"left": None, "center": None, "right": None}