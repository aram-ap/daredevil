#pragma once

// Plays an event vibration pattern (boot, link lost, low battery, ...).
// No hardware calls: main.cpp asks duty() for each motor and applies it to PWM.

#include <stdint.h>

#include "protocol.h"

// One step: a strength (0..255) for every motor, held for ms milliseconds.
struct PatternStep {
  uint8_t duty[proto::NUM_MOTORS];
  uint16_t ms;
};

// A pattern: its steps played in order, the whole sequence `repeats` times.
struct Pattern {
  const PatternStep *steps;
  uint8_t numSteps;
  uint8_t repeats;
};

class PatternPlayer {
 public:
  // Start a pattern now, replacing any pattern already playing.
  void play(const Pattern &pattern, uint32_t nowMs) {
    pattern_ = &pattern;
    startMs_ = nowMs;
    current_ = pattern.numSteps > 0 ? &pattern.steps[0] : nullptr;
  }

  void stop() {
    pattern_ = nullptr;
    current_ = nullptr;
  }

  // Call every loop. Works out the current step from the time since play(),
  // so a late call still lands on the right step instead of falling behind.
  // Unsigned subtraction keeps this correct across millis() wraparound.
  void update(uint32_t nowMs) {
    if (pattern_ == nullptr) return;

    uint32_t roundMs = 0;
    for (uint8_t i = 0; i < pattern_->numSteps; i++) roundMs += pattern_->steps[i].ms;

    const uint32_t elapsed = nowMs - startMs_;
    if (roundMs == 0 || elapsed >= roundMs * pattern_->repeats) {
      stop();  // finished (also covers an empty pattern or 0 repeats)
      return;
    }

    uint32_t t = elapsed % roundMs;  // position within the current round
    for (uint8_t i = 0; i < pattern_->numSteps; i++) {
      if (t < pattern_->steps[i].ms) {
        current_ = &pattern_->steps[i];
        return;
      }
      t -= pattern_->steps[i].ms;
    }
  }

  bool active() const { return current_ != nullptr; }

  uint8_t duty(uint8_t index) const {
    return (current_ != nullptr && index < proto::NUM_MOTORS) ? current_->duty[index] : 0;
  }

 private:
  const Pattern *pattern_ = nullptr;
  const PatternStep *current_ = nullptr;
  uint32_t startMs_ = 0;
};
