// Daredevil bracelet firmware: receive motor commands from the Jetson over USB
// serial, drive the vibration motors with PWM, and fail safe (motors off) if
// the link goes quiet.

#include <Arduino.h>

#include "config.h"
#include "protocol.h"

static proto::Parser parser;
static uint32_t lastValidFrameMs = 0;
static bool motorsActive = false;

// --- motors ---------------------------------------------------------------

// arduino-esp32 3.x addresses PWM by pin; 2.x (PlatformIO's default) by channel.
static void motorsBegin() {
  for (uint8_t i = 0; i < NUM_MOTORS; i++) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcAttach(MOTOR_PINS[i], MOTOR_PWM_FREQ_HZ, MOTOR_PWM_RESOLUTION_BITS);
#else
    ledcSetup(i, MOTOR_PWM_FREQ_HZ, MOTOR_PWM_RESOLUTION_BITS);
    ledcAttachPin(MOTOR_PINS[i], i);
#endif
  }
}

static void motorWrite(uint8_t index, uint8_t duty) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(MOTOR_PINS[index], duty);
#else
  ledcWrite(index, duty);
#endif
}

static void motorsOff() {
  for (uint8_t i = 0; i < NUM_MOTORS; i++) motorWrite(i, 0);
  motorsActive = false;
}

// --- replies --------------------------------------------------------------

static uint8_t txSeq = 0;

static void sendFrame(uint8_t type, uint8_t seq, const uint8_t *payload, uint8_t len) {
  uint8_t buf[proto::MAX_FRAME];
  size_t n = proto::encode(type, seq, payload, len, buf);
  Serial.write(buf, n);
}

static void sendAck(const proto::Frame &f, uint8_t status) {
  uint8_t payload[2] = {f.type, status};
  sendFrame(proto::MSG_ACK, f.seq, payload, sizeof(payload));
}

static void sendIdentity() {
  uint8_t payload[4] = {BRACELET_SIDE, FW_VERSION_MAJOR, FW_VERSION_MINOR, NUM_MOTORS};
  sendFrame(proto::MSG_IDENTITY, txSeq++, payload, sizeof(payload));
}

// --- message handling -----------------------------------------------------

static void handleFrame(const proto::Frame &f) {
  // Any well-formed frame proves the Jetson is alive.
  lastValidFrameMs = millis();

  switch (f.type) {
    case proto::MSG_SET_MOTORS:
      if (f.len != NUM_MOTORS) {
        sendAck(f, proto::STATUS_BAD_LENGTH);
        return;
      }
      for (uint8_t i = 0; i < NUM_MOTORS; i++) motorWrite(i, f.payload[i]);
      motorsActive = true;
      sendAck(f, proto::STATUS_OK);
      break;
    case proto::MSG_HEARTBEAT:
      sendAck(f, proto::STATUS_OK);
      break;
    case proto::MSG_IDENTIFY:
      sendIdentity();
      break;
    default:
      sendAck(f, proto::STATUS_UNKNOWN_TYPE);
      break;
  }
}

// --- main -----------------------------------------------------------------

void setup() {
  motorsBegin();
  motorsOff();

  Serial.begin(115200);  // baud is ignored on native USB
  // Don't block in Serial.write() when the Jetson isn't reading or isn't
  // plugged in -- that would also stall the link watchdog below.
  Serial.setTxTimeoutMs(0);
}

void loop() {
  while (Serial.available() > 0) {
    if (parser.feed((uint8_t)Serial.read())) handleFrame(parser.frame);
  }

  if (motorsActive && millis() - lastValidFrameMs > LINK_TIMEOUT_MS) {
    motorsOff();
  }
}
