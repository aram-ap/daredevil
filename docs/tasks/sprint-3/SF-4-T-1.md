---
id: SF-4-T-1
story: SF-4
sprint: 3
assignee: Ilya Krasnyy
estimate_hours: 8
---

# Play event vibration patterns on the bracelet and warn when the link drops

## Description
Serves SF-4 (distinct warning when battery is low or the wireless link drops, so silence is not mistaken for a clear path). The bracelet firmware gets a small, editable table of vibration patterns (boot, link lost, low battery) and a player that runs them. The bracelet plays the link-lost pattern by itself when the Jetson stops sending, and the Jetson can ask for any pattern with a new `PLAY_PATTERN` message.
Implemented and merged in PR #17 and PR #20 (`source/esp32/`, `source/jetson/`); this task file records the work and maps each criterion to its existing test.
Out of scope: the low-battery trigger (SF-4-T-2), choosing final strengths and timings on the real bracelet (placeholders for now), and distance-scaled strength (SF-2).

## Specs
- `source/esp32/include/pattern_player.h`: `PatternStep { duty[4], ms }`, `Pattern { steps, numSteps, repeats }`, and `PatternPlayer` with `play(pattern, nowMs)`, `stop()`, `update(nowMs)`, `active()`, `duty(i)`.
  - `update` finds the current step from the time since `play`, so a late call lands on the right step. The pattern stops after `repeats` rounds. Unsigned math keeps it correct across `millis()` wraparound.
  - `play` replaces any pattern already playing.
- `source/esp32/include/patterns.h`: ids `BOOT = 0`, `LINK_LOST = 1`, `LOW_BATTERY = 2`, `COUNT`, and `ALL[]` indexed by id. Every pattern has at least one step, at least one round and no 0 ms step.
- `source/esp32/include/output.h`: `outputDuty(player, controller, i)` returns the pattern's strength while a pattern plays, otherwise the Jetson's.
- Link lost: when no `SET_MOTORS` arrives for 500 ms (`Controller::DEFAULT_LINK_TIMEOUT_MS`), the motors turn off and `LINK_LOST` plays once. `BOOT` plays once at power-up.
- Protocol: `PLAY_PATTERN = 0x04` with payload `[pattern_id]`. The bracelet ACKs `OK` and plays it, `BAD_LENGTH` if the payload is not 1 byte, or `BAD_ARGUMENT (0x03)` for an unknown id.
- Jetson: `protocol.PATTERNS = {"boot": 0, "link_lost": 1, "low_battery": 2}` and `Bracelet.play_pattern(id)`, which raises `ValueError` for an unknown id and sends nothing. `examples/play_pattern.py` plays a pattern over USB or Wi-Fi.

## Requirements
- Pattern logic has no hardware calls, so it runs in `pio test -e native` on a laptop.
- Pattern ids are the same in `patterns.h` and `protocol.py`.
- Existing firmware and Python tests keep passing.

## Acceptance criteria
1. A pattern starts on its first step, moves to the next step exactly when the step's time is up, repeats `repeats` times and then stops (`test_patterns`: `test_play_starts_on_the_first_step`, `test_moves_to_the_next_step_exactly_when_its_time_is_up`, `test_repeats_the_right_number_of_times_then_stops`).
2. A late `update` lands on the right step, a new pattern replaces the playing one, and timing is correct across `millis()` wraparound (`test_a_late_update_lands_on_the_right_step`, `test_a_new_pattern_replaces_the_one_playing`, `test_works_across_millis_wraparound`).
3. Every built-in pattern is playable (`test_built_in_patterns_are_playable`).
4. A playing pattern overrides the Jetson's motor command, and the Jetson's command takes over again when it ends; if the link died meanwhile the motors stay off (`test_a_playing_pattern_overrides_the_jetson`, `test_the_jetson_takes_over_again_when_the_pattern_ends`, `test_motors_stay_off_after_the_pattern_if_the_link_died_meanwhile`).
5. `PLAY_PATTERN` with a known id is ACKed `OK` and requested once; an unknown id gives `BAD_ARGUMENT` and a wrong length gives `BAD_LENGTH` (`test_controller`: `test_play_pattern_requests_the_pattern_and_acks`, `test_play_pattern_with_unknown_id_is_rejected`, `test_play_pattern_with_wrong_length_is_rejected`).
6. Pattern ids match between firmware and Python, and `Bracelet.play_pattern` sends one frame for a known id and nothing for an unknown one (`test_pattern_ids_match_the_python_side`, `test_bracelet.py`: `test_pattern_ids_match_the_firmware`, `test_play_pattern_sends_one_frame`, `test_play_pattern_rejects_unknown_ids_and_sends_nothing`).
7. On the wrist PCB, boot, link-lost and low-battery patterns are felt, and the link-lost pattern plays within about 0.5 s of the Jetson stopping (checked by hand over USB from the Mac).
