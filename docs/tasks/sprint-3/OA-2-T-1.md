---
id: OA-2-T-1
story: OA-2
sprint: 3
assignee: Kaleb Kasparian
estimate_hours: 4
---

# Filter transient noise and confirm directional obstacles per zone

## Description
Serves OA-2 (sort obstacles into left, right, and center zones and feel them on matching motors). This task covers slicing a 2D depth frame into left, center, and right columns with an 8% minimum pixel-coverage filter to reject thin noise artifacts, and confirming obstacles independently per zone across consecutive frames with dropout hysteresis. Hardware IMU pitch projection (`obstacle_filter.py`) and serial link packet transmission (`daredevil_link`) are out of scope.

## Specs
- In `depth-zones/zone_depth.py`, `extract_filtered_zone_distances(depth_m, min_depth=0.5, max_depth=3.0, min_coverage_ratio=0.08)` accepts a 2D NumPy depth array `(H, W)` in meters and partitions it horizontally into `"left"` (`0:W//3`), `"center"` (`W//3:2*(W//3)`), and `"right"` (`2*(W//3):W`).
- If `depth_m` is not a 2D array or has width `< 3`, `extract_filtered_zone_distances` raises `ValueError("depth_m must be a 2D array with width >= 3")`.
- Only finite pixels satisfying `min_depth <= pixel <= max_depth` are treated as valid obstacle readings. If valid pixels make up strictly less than `min_coverage_ratio` of a zone's total pixels, that zone returns `None`; otherwise it returns the 5th-percentile valid depth as a `float`.
- In `depth-zones/zone_depth.py`, `DirectionalZoneConfirm(confirm_frames=3, clear_frames=2)` maintains independent state for `"left"`, `"center"`, and `"right"`, raising `ValueError` if `confirm_frames < 1` or `clear_frames < 1`.
- `DirectionalZoneConfirm.update(raw_zones)` returns `None` for an unconfirmed zone until it receives non-`None` distances for `confirm_frames` consecutive calls, and once confirmed, retains the last confirmed distance during brief dropouts until `clear_frames` consecutive `None` calls occur in that zone.

## Requirements
- Implement in `depth-zones/zone_depth.py` while keeping `compute_zone_distances` and `ZoneStabilizer` intact for existing callers.
- Use only `numpy` and the Python standard library; add no new runtime dependencies.
- Existing tests must keep passing.

## Acceptance criteria
1. `extract_filtered_zone_distances` splits a 2D depth array into `"left"`, `"center"`, and `"right"` zones and returns the 5th-percentile valid distance within `[min_depth, max_depth]` for each populated zone.
2. `extract_filtered_zone_distances` returns `None` for any zone where valid pixels cover less than `min_coverage_ratio` of the zone area, and raises `ValueError` for non-2D inputs or width `< 3`.
3. `DirectionalZoneConfirm.update` suppresses obstacles present for fewer than `confirm_frames` consecutive frames and outputs the confirmed distance on the `confirm_frames`-th consecutive frame independently per zone.
4. Once a zone is confirmed, `DirectionalZoneConfirm.update` retains the last confirmed distance across a single-frame dropout and resets to `None` after `clear_frames` consecutive `None` frames.