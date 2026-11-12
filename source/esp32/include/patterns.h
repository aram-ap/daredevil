#pragma once

// Event vibration patterns: THE TEMPLATE TO EDIT.
//
// Each step is { {motor 0, motor 1, motor 2, motor 3}, milliseconds }, with
// strengths 0..255 (0 = off). A pattern plays its steps in order, `repeats`
// times. While a pattern plays it overrides the Jetson's motor commands.
//
// To add a pattern: add its steps and a Pattern below, add an Id before COUNT,
// and add it to ALL in the same order. test_patterns checks every pattern here
// is playable (at least one step and one round, no 0 ms step).
//
// PLACEHOLDER strengths and timings -- tune them on the real bracelet.

#include <stddef.h>

#include "pattern_player.h"

namespace patterns {

// Builds a Pattern and counts the steps for you, so the count can't be wrong.
template <size_t N>
constexpr Pattern make(const PatternStep (&steps)[N], uint8_t repeats) {
  return Pattern{steps, static_cast<uint8_t>(N), repeats};
}

// Boot: two short soft pulses on all motors ("I'm on").
static const PatternStep BOOT_STEPS[] = {
    {{102, 102, 102, 102}, 100},  // ~40%
    {{0, 0, 0, 0}, 100},
};
static const Pattern BOOT_PATTERN = make(BOOT_STEPS, 2);

// Link lost: one sweep across the motors ("the Jetson stopped talking").
static const PatternStep LINK_LOST_STEPS[] = {
    {{180, 0, 0, 0}, 120},
    {{0, 180, 0, 0}, 120},
    {{0, 0, 180, 0}, 120},
    {{0, 0, 0, 180}, 120},
};
static const Pattern LINK_LOST_PATTERN = make(LINK_LOST_STEPS, 1);

// Low battery: three long strong pulses on all motors.
static const PatternStep LOW_BATTERY_STEPS[] = {
    {{179, 179, 179, 179}, 300},  // ~70%
    {{0, 0, 0, 0}, 200},
};
static const Pattern LOW_BATTERY_PATTERN = make(LOW_BATTERY_STEPS, 3);

enum Id : uint8_t { BOOT, LINK_LOST, LOW_BATTERY, COUNT };

// Indexed by Id.
static const Pattern *const ALL[COUNT] = {
    &BOOT_PATTERN,
    &LINK_LOST_PATTERN,
    &LOW_BATTERY_PATTERN,
};

inline const Pattern &get(Id id) { return *ALL[id]; }

}  // namespace patterns
