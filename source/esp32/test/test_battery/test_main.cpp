// BatteryMonitor: turns battery readings (millivolts) into a single
// "battery just went low" event. Hysteresis: low below lowMv, only cleared again
// at or above clearMv, so a voltage hovering near the threshold doesn't keep
// re-triggering the low-battery pattern.
// Hardware-free: main.cpp reads the voltage divider on D0 and passes millivolts in.

#include <unity.h>

#include "battery_monitor.h"

void setUp() {}
void tearDown() {}

// Placeholder thresholds for these tests only; the real ones live in config.h.
static const uint16_t LOW_MV = 3500;
static const uint16_t CLEAR_MV = 3700;

void test_a_healthy_battery_gives_no_event() {
  BatteryMonitor m(LOW_MV, CLEAR_MV);
  TEST_ASSERT_FALSE(m.update(4100));
  TEST_ASSERT_FALSE(m.update(3800));
  TEST_ASSERT_FALSE(m.update(3500));  // exactly the threshold is not low yet
  TEST_ASSERT_FALSE(m.low());
}

void test_dropping_below_the_threshold_gives_exactly_one_event() {
  BatteryMonitor m(LOW_MV, CLEAR_MV);
  m.update(4000);
  TEST_ASSERT_TRUE(m.update(3499));
  TEST_ASSERT_TRUE(m.low());
  TEST_ASSERT_FALSE(m.update(3450));  // still low: no new event
  TEST_ASSERT_FALSE(m.update(3300));
}

void test_noise_around_the_threshold_does_not_retrigger() {
  BatteryMonitor m(LOW_MV, CLEAR_MV);
  m.update(4000);
  TEST_ASSERT_TRUE(m.update(3490));
  // A real battery reading wobbles; none of these climb back to CLEAR_MV.
  TEST_ASSERT_FALSE(m.update(3550));
  TEST_ASSERT_FALSE(m.update(3480));
  TEST_ASSERT_FALSE(m.update(3699));
  TEST_ASSERT_FALSE(m.update(3495));
  TEST_ASSERT_TRUE(m.low());
}

void test_already_low_at_boot_gives_an_event() {
  BatteryMonitor m(LOW_MV, CLEAR_MV);
  TEST_ASSERT_TRUE(m.update(3300));  // first reading after power-up
}

void test_rearms_after_the_battery_recovers() {
  // E.g. the battery was charged: a later drop is a new event.
  BatteryMonitor m(LOW_MV, CLEAR_MV);
  TEST_ASSERT_TRUE(m.update(3400));
  TEST_ASSERT_FALSE(m.update(3700));  // recovered: cleared, but no event
  TEST_ASSERT_FALSE(m.low());
  TEST_ASSERT_TRUE(m.update(3400));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_a_healthy_battery_gives_no_event);
  RUN_TEST(test_dropping_below_the_threshold_gives_exactly_one_event);
  RUN_TEST(test_noise_around_the_threshold_does_not_retrigger);
  RUN_TEST(test_already_low_at_boot_gives_an_event);
  RUN_TEST(test_rearms_after_the_battery_recovers);
  return UNITY_END();
}
