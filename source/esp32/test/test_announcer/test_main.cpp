// Announcer: when a bracelet should broadcast its IDENTITY over Wi-Fi.
// Rule: announce every 1000 ms while no Jetson frame has arrived over Wi-Fi in
// the last 500 ms; stay quiet while the link is active.

#include <unity.h>

#include "announcer.h"

void setUp() {}
void tearDown() {}

void test_announces_immediately_after_boot() {
  Announcer a(1000, 500);
  TEST_ASSERT_TRUE(a.shouldAnnounce(0));
}

void test_repeats_every_period_while_unlinked() {
  Announcer a(1000, 500);
  TEST_ASSERT_TRUE(a.shouldAnnounce(0));
  TEST_ASSERT_FALSE(a.shouldAnnounce(999));
  TEST_ASSERT_TRUE(a.shouldAnnounce(1000));
  TEST_ASSERT_FALSE(a.shouldAnnounce(1999));
  TEST_ASSERT_TRUE(a.shouldAnnounce(2000));
}

void test_stays_quiet_while_jetson_frames_keep_arriving() {
  Announcer a(1000, 500);
  a.shouldAnnounce(0);
  for (uint32_t t = 100; t <= 5000; t += 50) {
    a.onLinkFrame(t);
    TEST_ASSERT_FALSE(a.shouldAnnounce(t + 10));
  }
}

void test_resumes_right_after_link_goes_silent() {
  Announcer a(1000, 500);
  a.shouldAnnounce(0);
  a.onLinkFrame(300);
  TEST_ASSERT_FALSE(a.shouldAnnounce(800));  // exactly 500 ms: still linked
  // Silent now. Only 801 ms since the last announcement, less than a period,
  // but the Jetson has gone away, so announce at once instead of waiting.
  TEST_ASSERT_TRUE(a.shouldAnnounce(801));
  TEST_ASSERT_FALSE(a.shouldAnnounce(1800));
  TEST_ASSERT_TRUE(a.shouldAnnounce(1801));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_announces_immediately_after_boot);
  RUN_TEST(test_repeats_every_period_while_unlinked);
  RUN_TEST(test_stays_quiet_while_jetson_frames_keep_arriving);
  RUN_TEST(test_resumes_right_after_link_goes_silent);
  return UNITY_END();
}
