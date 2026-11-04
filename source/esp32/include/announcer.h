#pragma once

// Decides when the bracelet broadcasts its IDENTITY over Wi-Fi so the Jetson
// can find it. Announces every periodMs while no Jetson frame has arrived over
// Wi-Fi within silenceMs, and at once when an active link goes silent.

#include <stdint.h>

class Announcer {
 public:
  Announcer(uint32_t periodMs, uint32_t silenceMs) : periodMs_(periodMs), silenceMs_(silenceMs) {}

  // A valid frame from the Jetson arrived over Wi-Fi.
  void onLinkFrame(uint32_t nowMs) {
    lastFrameMs_ = nowMs;
    linked_ = true;
  }

  // Returns true when an announcement should be sent now (and counts it as sent).
  bool shouldAnnounce(uint32_t nowMs) {
    if (linked_) {
      if (nowMs - lastFrameMs_ <= silenceMs_) return false;
      linked_ = false;  // the Jetson just went quiet: announce without waiting a period
      return announce(nowMs);
    }
    if (announced_ && nowMs - lastAnnounceMs_ < periodMs_) return false;
    return announce(nowMs);
  }

 private:
  bool announce(uint32_t nowMs) {
    announced_ = true;
    lastAnnounceMs_ = nowMs;
    return true;
  }

  uint32_t periodMs_;
  uint32_t silenceMs_;
  bool linked_ = false;
  uint32_t lastFrameMs_ = 0;
  bool announced_ = false;
  uint32_t lastAnnounceMs_ = 0;
};
