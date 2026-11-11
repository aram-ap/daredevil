#pragma once

// Turns battery readings into a single "battery just went low" event.
// Hysteresis: the battery counts as low below lowMv, and only counts as
// recovered at or above clearMv. A reading hovering around lowMv therefore
// warns once instead of on every wobble.
// No hardware calls: main.cpp reads the voltage divider and passes millivolts in.

#include <stdint.h>

class BatteryMonitor {
 public:
  BatteryMonitor(uint16_t lowMv, uint16_t clearMv) : lowMv_(lowMv), clearMv_(clearMv) {}

  // Feed one reading. Returns true only at the moment the battery becomes low.
  bool update(uint16_t batteryMv) {
    if (low_) {
      if (batteryMv >= clearMv_) low_ = false;  // recovered (e.g. charged): re-arm
      return false;
    }
    if (batteryMv < lowMv_) {
      low_ = true;
      return true;
    }
    return false;
  }

  bool low() const { return low_; }

 private:
  uint16_t lowMv_;
  uint16_t clearMv_;
  bool low_ = false;
};
