#pragma once

// What the bracelet does with each frame, plus the link watchdog.
// No hardware calls: main.cpp applies duty() to PWM and sends the reply bytes
// back on whichever link (USB or Wi-Fi) the frame came from.

#include <stddef.h>
#include <stdint.h>

#include "protocol.h"

class Controller {
 public:
  static constexpr uint32_t DEFAULT_LINK_TIMEOUT_MS = 500;

  Controller(uint8_t side, uint8_t fwMajor, uint8_t fwMinor,
             uint32_t linkTimeoutMs = DEFAULT_LINK_TIMEOUT_MS)
      : side_(side), fwMajor_(fwMajor), fwMinor_(fwMinor), linkTimeoutMs_(linkTimeoutMs) {}

  // Act on one valid frame. Writes the reply into out (at least MAX_FRAME
  // bytes) and returns its length; every frame gets a reply.
  size_t handleFrame(const proto::Frame &f, uint32_t nowMs, uint8_t *out) {
    lastFrameMs_ = nowMs;  // any valid frame proves the Jetson is alive

    switch (f.type) {
      case proto::MSG_SET_MOTORS:
        if (f.len != proto::NUM_MOTORS) return ack(f, proto::STATUS_BAD_LENGTH, out);
        for (uint8_t i = 0; i < proto::NUM_MOTORS; i++) duties_[i] = f.payload[i];
        active_ = true;
        return ack(f, proto::STATUS_OK, out);
      case proto::MSG_HEARTBEAT:
        return ack(f, proto::STATUS_OK, out);
      case proto::MSG_IDENTIFY:
        return identityFrame(out);
      default:
        return ack(f, proto::STATUS_UNKNOWN_TYPE, out);
    }
  }

  // Call every loop. Returns true only at the moment the watchdog turns the
  // motors off. Unsigned subtraction keeps this correct across millis() wraparound.
  bool tick(uint32_t nowMs) {
    if (!active_ || nowMs - lastFrameMs_ <= linkTimeoutMs_) return false;
    for (uint8_t i = 0; i < proto::NUM_MOTORS; i++) duties_[i] = 0;
    active_ = false;
    return true;
  }

  // IDENTITY frame: the reply to IDENTIFY, and the Wi-Fi announcement.
  size_t identityFrame(uint8_t *out) {
    const uint8_t payload[4] = {side_, fwMajor_, fwMinor_, proto::NUM_MOTORS};
    return proto::encode(proto::MSG_IDENTITY, txSeq_++, payload, sizeof(payload), out);
  }

  uint8_t duty(uint8_t index) const { return index < proto::NUM_MOTORS ? duties_[index] : 0; }
  bool motorsActive() const { return active_; }

 private:
  size_t ack(const proto::Frame &f, uint8_t status, uint8_t *out) {
    const uint8_t payload[2] = {f.type, status};
    return proto::encode(proto::MSG_ACK, f.seq, payload, sizeof(payload), out);
  }

  uint8_t side_;
  uint8_t fwMajor_;
  uint8_t fwMinor_;
  uint32_t linkTimeoutMs_;
  uint8_t duties_[proto::NUM_MOTORS] = {};
  bool active_ = false;
  uint32_t lastFrameMs_ = 0;
  uint8_t txSeq_ = 0;
};
