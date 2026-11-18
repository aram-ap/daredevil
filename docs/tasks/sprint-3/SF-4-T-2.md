---
id: SF-4-T-2
story: SF-4
sprint: 3
assignee: Ilya Krasnyy
estimate_hours: 10
---

# Warn once on the bracelet when its battery runs low

## Description
Serves SF-4 (distinct warning when battery is low or the wireless link drops). The bracelet reads its own battery voltage and plays the low-battery pattern (from SF-4-T-1) when the voltage falls below a threshold. A reading that wobbles around the threshold warns only once.
Implemented and merged in PR #17 and PR #20 (`source/esp32/`); this task file records the work and maps each criterion to its existing test.
Out of scope: the pattern player itself (SF-4-T-1), reporting battery level to the Jetson, and calibrating the thresholds against a multimeter (still placeholders).

## Specs
- `source/esp32/include/battery_monitor.h`: `BatteryMonitor(lowMv, clearMv)` with `update(batteryMv) -> bool` and `low()`.
  - `update` returns `true` only at the moment the battery becomes low (reading `< lowMv`).
  - Once low, it stays low and returns `false` until a reading is `>= clearMv`, which re-arms it (hysteresis).
- `source/esp32/include/config.h`: `BATTERY_PIN 2` (D0, through the PCB's 100k/100k divider), `BATTERY_DIVIDER 2`, `BATTERY_SAMPLES 8`, `BATTERY_CHECK_MS 1000`, `BATTERY_LOW_MV 3500`, `BATTERY_CLEAR_MV 3700`.
- `source/esp32/src/main.cpp`: every `BATTERY_CHECK_MS`, average `BATTERY_SAMPLES` readings of `analogReadMilliVolts(BATTERY_PIN)`, multiply by `BATTERY_DIVIDER`, and feed the result to `BatteryMonitor`. On `true`, play `patterns::LOW_BATTERY`.
- Edge case: a battery already low at power-up warns on the first check.

## Requirements
- `BatteryMonitor` has no hardware calls, so it runs in `pio test -e native`.
- Thresholds live in `config.h` only.
- Existing firmware tests keep passing.

## Acceptance criteria
1. A healthy battery gives no warning (`test_battery`: `test_a_healthy_battery_gives_no_event`).
2. Dropping below `lowMv` gives exactly one warning (`test_dropping_below_the_threshold_gives_exactly_one_event`).
3. Readings wobbling between `lowMv` and `clearMv` do not warn again (`test_noise_around_the_threshold_does_not_retrigger`).
4. A battery already low at boot warns (`test_already_low_at_boot_gives_an_event`).
5. After a reading at or above `clearMv`, a new drop warns again (`test_rearms_after_the_battery_recovers`).

