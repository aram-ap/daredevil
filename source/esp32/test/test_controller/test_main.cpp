// Controller: what the bracelet does with each frame, and the link watchdog.
// Hardware-free: the controller only records duties; main.cpp applies them to PWM.

#include <unity.h>

#include "controller.h"
#include "protocol.h"

using namespace proto;

static const uint8_t SIDE_RIGHT = 1;

void setUp() {}
void tearDown() {}

static Frame makeFrame(uint8_t type, uint8_t seq, const uint8_t *payload, uint8_t len) {
  Frame f{};
  f.type = type;
  f.seq = seq;
  f.len = len;
  for (uint8_t i = 0; i < len; i++) f.payload[i] = payload[i];
  return f;
}

// Decode the reply bytes the controller produced.
static Frame decodeReply(const uint8_t *out, size_t n) {
  Parser parser;
  for (size_t i = 0; i < n; i++) {
    if (parser.feed(out[i])) return parser.frame;
  }
  TEST_FAIL_MESSAGE("reply is not a valid frame");
  return Frame{};
}

static const uint8_t ON[4] = {0, 180, 180, 0};

void test_motors_start_off() {
  Controller c(SIDE_RIGHT, 0, 1);
  for (uint8_t i = 0; i < 4; i++) TEST_ASSERT_EQUAL(0, c.duty(i));
  TEST_ASSERT_FALSE(c.motorsActive());
}

void test_set_motors_sets_duties_and_acks() {
  Controller c(SIDE_RIGHT, 0, 1);
  uint8_t out[MAX_FRAME];
  size_t n = c.handleFrame(makeFrame(MSG_SET_MOTORS, 7, ON, 4), 1000, out);

  TEST_ASSERT_EQUAL(180, c.duty(1));
  TEST_ASSERT_EQUAL(180, c.duty(2));
  TEST_ASSERT_TRUE(c.motorsActive());
  Frame reply = decodeReply(out, n);
  TEST_ASSERT_EQUAL_HEX8(MSG_ACK, reply.type);
  TEST_ASSERT_EQUAL(7, reply.seq);  // echoes the command's seq
  TEST_ASSERT_EQUAL_HEX8(MSG_SET_MOTORS, reply.payload[0]);
  TEST_ASSERT_EQUAL_HEX8(STATUS_OK, reply.payload[1]);
}

void test_set_motors_with_wrong_length_is_rejected() {
  Controller c(SIDE_RIGHT, 0, 1);
  uint8_t out[MAX_FRAME];
  size_t n = c.handleFrame(makeFrame(MSG_SET_MOTORS, 2, ON, 3), 1000, out);

  for (uint8_t i = 0; i < 4; i++) TEST_ASSERT_EQUAL(0, c.duty(i));
  TEST_ASSERT_EQUAL_HEX8(STATUS_BAD_LENGTH, decodeReply(out, n).payload[1]);
}

void test_heartbeat_is_acked() {
  Controller c(SIDE_RIGHT, 0, 1);
  uint8_t out[MAX_FRAME];
  Frame reply = decodeReply(out, c.handleFrame(makeFrame(MSG_HEARTBEAT, 4, nullptr, 0), 1000, out));
  TEST_ASSERT_EQUAL_HEX8(MSG_ACK, reply.type);
  TEST_ASSERT_EQUAL(4, reply.seq);
  TEST_ASSERT_EQUAL_HEX8(STATUS_OK, reply.payload[1]);
}

void test_unknown_type_is_reported() {
  Controller c(SIDE_RIGHT, 0, 1);
  uint8_t out[MAX_FRAME];
  Frame reply = decodeReply(out, c.handleFrame(makeFrame(0x42, 1, nullptr, 0), 1000, out));
  TEST_ASSERT_EQUAL_HEX8(0x42, reply.payload[0]);
  TEST_ASSERT_EQUAL_HEX8(STATUS_UNKNOWN_TYPE, reply.payload[1]);
}

void test_identify_reports_side_version_and_motor_count() {
  Controller c(SIDE_RIGHT, 0, 1);
  uint8_t out[MAX_FRAME];
  Frame reply = decodeReply(out, c.handleFrame(makeFrame(MSG_IDENTIFY, 0, nullptr, 0), 1000, out));
  TEST_ASSERT_EQUAL_HEX8(MSG_IDENTITY, reply.type);
  TEST_ASSERT_EQUAL(4, reply.len);
  const uint8_t expected[4] = {SIDE_RIGHT, 0, 1, 4};
  TEST_ASSERT_EQUAL_HEX8_ARRAY(expected, reply.payload, 4);
}

void test_identity_frame_is_available_for_announcements() {
  Controller c(SIDE_RIGHT, 0, 1);
  uint8_t out[MAX_FRAME];
  Frame f = decodeReply(out, c.identityFrame(out));
  TEST_ASSERT_EQUAL_HEX8(MSG_IDENTITY, f.type);
  TEST_ASSERT_EQUAL(SIDE_RIGHT, f.payload[0]);
}

void test_watchdog_turns_motors_off_after_500ms_of_silence() {
  Controller c(SIDE_RIGHT, 0, 1);
  uint8_t out[MAX_FRAME];
  c.handleFrame(makeFrame(MSG_SET_MOTORS, 0, ON, 4), 1000, out);

  TEST_ASSERT_FALSE(c.tick(1500));  // exactly 500 ms: still on
  TEST_ASSERT_TRUE(c.motorsActive());
  TEST_ASSERT_TRUE(c.tick(1501));   // past 500 ms: just turned off
  TEST_ASSERT_FALSE(c.motorsActive());
  for (uint8_t i = 0; i < 4; i++) TEST_ASSERT_EQUAL(0, c.duty(i));
  TEST_ASSERT_FALSE(c.tick(1600));  // reports the change only once
}

void test_any_valid_frame_feeds_the_watchdog() {
  Controller c(SIDE_RIGHT, 0, 1);
  uint8_t out[MAX_FRAME];
  c.handleFrame(makeFrame(MSG_SET_MOTORS, 0, ON, 4), 1000, out);
  c.handleFrame(makeFrame(MSG_HEARTBEAT, 1, nullptr, 0), 1400, out);

  c.tick(1800);
  TEST_ASSERT_TRUE(c.motorsActive());
  TEST_ASSERT_EQUAL(180, c.duty(1));  // heartbeat keeps the last intensities
}

void test_watchdog_survives_millis_wraparound() {
  // millis() wraps to 0 after ~49.7 days; unsigned subtraction must still work.
  Controller c(SIDE_RIGHT, 0, 1);
  uint8_t out[MAX_FRAME];
  c.handleFrame(makeFrame(MSG_SET_MOTORS, 0, ON, 4), 0xFFFFFF00u, out);

  c.tick(0x000000F0u);  // 496 ms later
  TEST_ASSERT_TRUE(c.motorsActive());
  c.tick(0x00000110u);  // 528 ms later
  TEST_ASSERT_FALSE(c.motorsActive());
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_motors_start_off);
  RUN_TEST(test_set_motors_sets_duties_and_acks);
  RUN_TEST(test_set_motors_with_wrong_length_is_rejected);
  RUN_TEST(test_heartbeat_is_acked);
  RUN_TEST(test_unknown_type_is_reported);
  RUN_TEST(test_identify_reports_side_version_and_motor_count);
  RUN_TEST(test_identity_frame_is_available_for_announcements);
  RUN_TEST(test_watchdog_turns_motors_off_after_500ms_of_silence);
  RUN_TEST(test_any_valid_frame_feeds_the_watchdog);
  RUN_TEST(test_watchdog_survives_millis_wraparound);
  return UNITY_END();
}
