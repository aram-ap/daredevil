#pragma once

// Jetson <-> ESP32 bracelet wire protocol (v1).
//
//   | 0xAA | 0x55 | type | seq | len | payload (len B) | CRC-8 |
//
// CRC-8: poly 0x07, init 0x00, over type, seq, len, payload.
// Mirrors source/jetson/daredevil_link/protocol.py -- keep them in sync.

#include <stddef.h>
#include <stdint.h>

namespace proto {

constexpr uint8_t SYNC0 = 0xAA;
constexpr uint8_t SYNC1 = 0x55;
constexpr uint8_t MAX_PAYLOAD = 16;
constexpr size_t MAX_FRAME = 5 + MAX_PAYLOAD + 1;

// Jetson -> ESP32
constexpr uint8_t MSG_SET_MOTORS = 0x01;  // payload: NUM_MOTORS intensities
constexpr uint8_t MSG_HEARTBEAT = 0x02;   // payload: none
constexpr uint8_t MSG_IDENTIFY = 0x03;    // payload: none

// ESP32 -> Jetson
constexpr uint8_t MSG_ACK = 0x81;       // seq = echoed; payload: [acked_type, status]
constexpr uint8_t MSG_IDENTITY = 0x83;  // payload: [side, fw_major, fw_minor, num_motors]

constexpr uint8_t STATUS_OK = 0x00;
constexpr uint8_t STATUS_BAD_LENGTH = 0x01;
constexpr uint8_t STATUS_UNKNOWN_TYPE = 0x02;

inline uint8_t crc8(const uint8_t *data, size_t len, uint8_t crc = 0) {
  for (size_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (int b = 0; b < 8; b++) {
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
    }
  }
  return crc;
}

struct Frame {
  uint8_t type;
  uint8_t seq;
  uint8_t len;
  uint8_t payload[MAX_PAYLOAD];
};

// Writes a complete frame into out (at least MAX_FRAME bytes); returns its size.
inline size_t encode(uint8_t type, uint8_t seq, const uint8_t *payload, uint8_t len,
                     uint8_t *out) {
  out[0] = SYNC0;
  out[1] = SYNC1;
  out[2] = type;
  out[3] = seq;
  out[4] = len;
  for (uint8_t i = 0; i < len; i++) out[5 + i] = payload[i];
  out[5 + len] = crc8(out + 2, 3 + len);
  return 6 + len;
}

// Byte-at-a-time decoder. feed() returns true when `frame` holds a newly
// completed, CRC-checked frame. Invalid input is dropped and it re-hunts for sync.
class Parser {
 public:
  bool feed(uint8_t byte) {
    switch (state_) {
      case WAIT_SYNC0:
        if (byte == SYNC0) state_ = WAIT_SYNC1;
        break;
      case WAIT_SYNC1:
        if (byte == SYNC1) state_ = TYPE;
        else if (byte != SYNC0) state_ = WAIT_SYNC0;
        break;
      case TYPE:
        frame.type = byte;
        state_ = SEQ;
        break;
      case SEQ:
        frame.seq = byte;
        state_ = LEN;
        break;
      case LEN:
        if (byte > MAX_PAYLOAD) {
          state_ = WAIT_SYNC0;
        } else {
          frame.len = byte;
          index_ = 0;
          state_ = byte ? PAYLOAD : CRC;
        }
        break;
      case PAYLOAD:
        frame.payload[index_++] = byte;
        if (index_ == frame.len) state_ = CRC;
        break;
      case CRC: {
        state_ = WAIT_SYNC0;
        uint8_t header[3] = {frame.type, frame.seq, frame.len};
        uint8_t crc = crc8(header, 3);
        crc = crc8(frame.payload, frame.len, crc);
        if (crc == byte) return true;
        crc_errors++;
        break;
      }
    }
    return false;
  }

  Frame frame{};
  uint32_t crc_errors = 0;

 private:
  enum State { WAIT_SYNC0, WAIT_SYNC1, TYPE, SEQ, LEN, PAYLOAD, CRC };
  State state_ = WAIT_SYNC0;
  uint8_t index_ = 0;
};

}  // namespace proto
