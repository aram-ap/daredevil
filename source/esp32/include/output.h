#pragma once

// What actually reaches each motor: an event pattern, while one plays,
// overrides the Jetson's commands; otherwise the Jetson's strengths apply
// (which the watchdog has zeroed if the link went quiet).

#include <stdint.h>

#include "controller.h"
#include "pattern_player.h"

inline uint8_t outputDuty(const PatternPlayer &player, const Controller &controller,
                          uint8_t index) {
  return player.active() ? player.duty(index) : controller.duty(index);
}
