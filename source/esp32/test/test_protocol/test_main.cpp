// proto:: encoder and parser, checked against the Python implementation's bytes.

#include <unity.h>

#include "protocol.h"

using namespace proto;

void setUp() {}
void tearDown() {}

static bool feedAll(Parser &parser, const uint8_t *data, size_t len) {
  bool got = false;
  for (size_t i = 0; i < len; i++) got = parser.feed(data[i]) || got;
  return got;
}

void test_crc8_check_value() {
  const uint8_t check[] = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
  TEST_ASSERT_EQUAL_HEX8(0xF4, crc8(check, sizeof(check)));
}

void test_encode_matches_python_bytes() {
  // python: encode_frame(MSG_SET_MOTORS, 7, bytes([0, 180, 180, 0]))
  const uint8_t expected[] = {0xAA, 0x55, 0x01, 0x07, 0x04, 0x00, 0xB4, 0xB4, 0x00, 0xD5};
  const uint8_t payload[] = {0, 180, 180, 0};
  uint8_t out[MAX_FRAME];
  size_t n = encode(MSG_SET_MOTORS, 7, payload, sizeof(payload), out);
  TEST_ASSERT_EQUAL(sizeof(expected), n);
  TEST_ASSERT_EQUAL_HEX8_ARRAY(expected, out, n);
}

void test_parser_decodes_python_frame() {
  // python: encode_frame(MSG_ACK, 7, bytes([1, 0]))
  const uint8_t ack[] = {0xAA, 0x55, 0x81, 0x07, 0x02, 0x01, 0x00, 0x54};
  Parser parser;
  TEST_ASSERT_TRUE(feedAll(parser, ack, sizeof(ack)));
  TEST_ASSERT_EQUAL_HEX8(MSG_ACK, parser.frame.type);
  TEST_ASSERT_EQUAL(7, parser.frame.seq);
  TEST_ASSERT_EQUAL(2, parser.frame.len);
  TEST_ASSERT_EQUAL_HEX8(0x01, parser.frame.payload[0]);
}

void test_parser_rejects_bad_crc() {
  uint8_t frame[] = {0xAA, 0x55, 0x81, 0x07, 0x02, 0x01, 0x00, 0x54};
  frame[6] ^= 0xFF;
  Parser parser;
  TEST_ASSERT_FALSE(feedAll(parser, frame, sizeof(frame)));
  TEST_ASSERT_EQUAL(1, parser.crc_errors);
}

void test_reset_discards_truncated_datagram() {
  // Over UDP, one datagram = one frame. A truncated datagram must not swallow
  // the start of the next one, so the parser is reset between datagrams.
  const uint8_t truncated[] = {0xAA, 0x55, 0x01, 0x07, 0x04, 0x00};
  uint8_t good[MAX_FRAME];
  size_t n = encode(MSG_HEARTBEAT, 3, nullptr, 0, good);

  Parser parser;
  TEST_ASSERT_FALSE(feedAll(parser, truncated, sizeof(truncated)));
  parser.reset();
  TEST_ASSERT_TRUE(feedAll(parser, good, n));
  TEST_ASSERT_EQUAL_HEX8(MSG_HEARTBEAT, parser.frame.type);
  TEST_ASSERT_EQUAL(3, parser.frame.seq);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_crc8_check_value);
  RUN_TEST(test_encode_matches_python_bytes);
  RUN_TEST(test_parser_decodes_python_frame);
  RUN_TEST(test_parser_rejects_bad_crc);
  RUN_TEST(test_reset_discards_truncated_datagram);
  return UNITY_END();
}
