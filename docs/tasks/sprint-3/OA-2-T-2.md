---
id: OA-2-T-2
story: OA-2
sprint: 3
assignee: Kaleb Kasparian
estimate_hours: 2
---

# Confirm obstacles across consecutive frames independently per zone

## Description
Serves OA-2 (sort obstacles into left, right, and center zones and feel them on matching motors). This task extends multi-frame obstacle confirmation independently to the left, center, and right zones so transient depth flicker is suppressed while confirmed directional obstacles persist across brief sensor dropouts. Raw 2D depth frame slicing (`OA-2-T-1`) and hardware serial link transmission (`daredevil_link`) are out of scope.

## Specs
- In `depth-zones/zone_depth.py`, `DirectionalZoneConfirm(confirm_frames=3, clear_frames=2)` maintains independent temporal confirmation state for `"left"`, `"center"`, and `"right"`.
- Initializing `DirectionalZoneConfirm` with `confirm_frames < 1` or `clear_frames < 1` raises `ValueError("confirm_frames and clear_frames must be >= 1")`.
- `DirectionalZoneConfirm.update(raw_zones)` accepts a dict mapping zone names to `float | None` (missing keys, non-finite numbers, or values `<= 0.0` are treated as `None`) and returns a dict `{"left": float | None, "center": float | None, "right": float | None}`.
- An unconfirmed zone returns `None` until it receives valid distances for `confirm_frames` consecutive calls; a `None` reading before reaching `confirm_frames` resets that zone's consecutive hit counter to `0` without affecting other zones.
- Once confirmed, a zone returns its latest valid distance, retains its last confirmed distance across dropouts shorter than `clear_frames` consecutive `None` calls, and resets to unconfirmed (`None`) on the `clear_frames`-th consecutive `None` call.
- `DirectionalZoneConfirm.reset(zone=None)` clears confirmation state and counters for all zones when `zone is None`, or for a single zone (`"left"`, `"center"`, or `"right"`), raising `KeyError` for an unknown zone name.

## Requirements
- Implement in `depth-zones/zone_depth.py` while keeping `compute_zone_distances`, `ZoneStabilizer`, and `extract_filtered_zone_distances` intact.
- Use only `numpy` and the Python standard library; add no new runtime dependencies.
- Existing tests must keep passing.

## Acceptance criteria
1. `DirectionalZoneConfirm.update` suppresses obstacles present for fewer than `confirm_frames` consecutive frames and outputs the confirmed distance on the `confirm_frames`-th consecutive frame.
2. Confirmation state is tracked independently per zone so a miss in one zone resets only that zone's unconfirmed counter while other zones confirm on schedule.
3. Once a zone is confirmed, `DirectionalZoneConfirm.update` retains the last confirmed distance across dropouts of fewer than `clear_frames` consecutive `None` frames and clears to `None` on the `clear_frames`-th consecutive `None` frame.
4. `DirectionalZoneConfirm` raises `ValueError` when `confirm_frames < 1` or `clear_frames < 1`, and `reset(zone)` resets either a single valid zone or all zones while raising `KeyError` for unknown zone names.