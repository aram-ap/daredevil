"""Unit tests for Task OA-2-T-1: extract_filtered_zone_distances.

Each test function starts with `test_OA_2_T_1_` and maps directly to one of the
four numbered acceptance criteria in `docs/tasks/sprint-3/OA-2-T-1.md`.
"""
import sys
from pathlib import Path
import numpy as np
import pytest

# Add depth-zones/ to sys.path so zone_depth can be imported directly by pytest.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "depth-zones"))

from zone_depth import extract_filtered_zone_distances


def test_OA_2_T_1_splits_zones_and_returns_5th_percentile_distance():
    """Criterion 1: Splits a 2D depth array into left, center, and right columns
    and returns the 5th-percentile valid distance within [min_depth, max_depth]."""
    # Create a 10x30 frame -> Left is cols 0..9, Center is cols 10..19, Right is cols 20..29.
    frame = np.zeros((10, 30), dtype=np.float32)
    frame[:, 0:10] = 1.2
    frame[:, 10:20] = 2.4
    frame[:, 20:30] = 0.8

    zones = extract_filtered_zone_distances(
        frame, min_depth=0.5, max_depth=3.0, min_coverage_ratio=0.08
    )

    assert zones["left"] == pytest.approx(1.2, abs=1e-4)
    assert zones["center"] == pytest.approx(2.4, abs=1e-4)
    assert zones["right"] == pytest.approx(0.8, abs=1e-4)


def test_OA_2_T_1_ignores_outliers_and_out_of_envelope_depths():
    """Criterion 2: Ignores single-pixel close-range outliers via the 5th-percentile
    statistic and ignores depths outside [min_depth, max_depth] (0.0, NaN, <0.5, >3.0)."""
    # Initialize entire frame to 4.5 m (beyond the 3.0 m max_depth envelope).
    frame = np.full((10, 30), 4.5, dtype=np.float32)

    # Left zone (100 pixels total): 99 pixels at 2.0 m, 1 pixel outlier at 0.55 m.
    # Because 1 pixel is only 1% of the zone, the 5th-percentile stays at 2.0 m.
    frame[:, 0:10] = 2.0
    frame[0, 0] = 0.55

    # Center zone: half < 0.5 m (0.2 m) and half NaN -> 0 valid pixels -> None.
    frame[0:5, 10:20] = 0.2
    frame[5:10, 10:20] = np.nan

    zones = extract_filtered_zone_distances(
        frame, min_depth=0.5, max_depth=3.0, min_coverage_ratio=0.08
    )

    assert zones["left"] == pytest.approx(2.0, abs=1e-3)
    assert zones["center"] is None
    assert zones["right"] is None


def test_OA_2_T_1_returns_none_when_valid_coverage_below_threshold():
    """Criterion 3: Returns None for any zone where valid pixels cover less than
    min_coverage_ratio of the zone's area."""
    # Each zone has 10 * 10 = 100 pixels. With min_coverage_ratio=0.08, at least 8 pixels must be valid.
    frame = np.zeros((10, 30), dtype=np.float32)
    frame[0, 0:7] = 1.5    # Left zone: 7 valid pixels (7% < 8% threshold) -> None
    frame[0, 10:18] = 1.5  # Center zone: 8 valid pixels (8% >= 8% threshold) -> 1.5 m

    zones = extract_filtered_zone_distances(
        frame, min_depth=0.5, max_depth=3.0, min_coverage_ratio=0.08
    )

    assert zones["left"] is None
    assert zones["center"] == pytest.approx(1.5, abs=1e-4)
    assert zones["right"] is None


def test_OA_2_T_1_raises_value_error_on_invalid_dimensions_or_bounds():
    """Criterion 4: Raises ValueError for non-2D arrays, width < 3, or invalid
    depth/coverage parameters."""
    # 1D array is invalid.
    with pytest.raises(ValueError, match="depth_m must be a 2D array with width >= 3"):
        extract_filtered_zone_distances(np.zeros((10,), dtype=np.float32))

    # Width of 2 cannot be split into 3 non-empty zones.
    with pytest.raises(ValueError, match="depth_m must be a 2D array with width >= 3"):
        extract_filtered_zone_distances(np.zeros((10, 2), dtype=np.float32))

    # min_depth >= max_depth is invalid.
    with pytest.raises(ValueError, match="invalid depth bounds or coverage ratio"):
        extract_filtered_zone_distances(np.zeros((10, 30)), min_depth=3.0, max_depth=1.0)

    # min_coverage_ratio <= 0.0 is invalid.
    with pytest.raises(ValueError, match="invalid depth bounds or coverage ratio"):
        extract_filtered_zone_distances(np.zeros((10, 30)), min_coverage_ratio=0.0)