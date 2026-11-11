// Event vibration patterns (boot, link lost, low battery).
// PatternPlayer: given the time, which strength each motor should have now.
// outputDuty(): while a pattern plays it overrides the Jetson's strengths.
// Hardware-free: main.cpp applies outputDuty() to the PWM pins.

#include <unity.h>

#include "controller.h"
#include "output.h"
#include "pattern_player.h"
#include "patterns.h"
#include "protocol.h"

using namespace proto;

void setUp() {}
void tearDown() {}

// Test-only patterns, so tuning the real ones in patterns.h never breaks these tests.
// BLINK: motor 0 at 100 for 100 ms, then motor 3 at 200 for 50 ms; 3 rounds = 450 ms.
static const PatternStep BLINK_STEPS[] = {
    {{100, 0, 0, 0}, 100},
    {{0, 0, 0, 200}, 50},
};
static const Pattern BLINK = {BLINK_STEPS, 2, 3};

// SOLID: every motor at 50 for 200 ms, once.
static const PatternStep SOLID_STEPS[] = {
    {{50, 50, 50, 50}, 200},
};
static const Pattern SOLID = {SOLID_STEPS, 1, 1};

static void assertDuties(const PatternPlayer &p, uint8_t m0, uint8_t m1, uint8_t m2, uint8_t m3) {
  TEST_ASSERT_EQUAL(m0, p.duty(0));
  TEST_ASSERT_EQUAL(m1, p.duty(1));
  TEST_ASSERT_EQUAL(m2, p.duty(2));
  TEST_ASSERT_EQUAL(m3, p.duty(3));
}

// --- PatternPlayer ---------------------------------------------------------

void test_idle_at_start() {
  PatternPlayer p;
  p.update(0);
  TEST_ASSERT_FALSE(p.active());
  assertDuties(p, 0, 0, 0, 0);
}

void test_play_starts_on_the_first_step() {
  PatternPlayer p;
  p.play(BLINK, 1000);
  p.update(1000);
  TEST_ASSERT_TRUE(p.active());
  assertDuties(p, 100, 0, 0, 0);
}

void test_moves_to_the_next_step_exactly_when_its_time_is_up() {
  PatternPlayer p;
  p.play(BLINK, 1000);
  p.update(1099);
  assertDuties(p, 100, 0, 0, 0);  // step 1 lasts 100 ms: 1000..1099
  p.update(1100);
  assertDuties(p, 0, 0, 0, 200);  // step 2: 1100..1149
  p.update(1149);
  assertDuties(p, 0, 0, 0, 200);
  p.update(1150);
  assertDuties(p, 100, 0, 0, 0);  // round 2 starts again at step 1
}

void test_repeats_the_right_number_of_times_then_stops() {
  PatternPlayer p;
  p.play(BLINK, 1000);
  p.update(1449);  // last ms of round 3, step 2
  TEST_ASSERT_TRUE(p.active());
  assertDuties(p, 0, 0, 0, 200);
  p.update(1450);  // 3 rounds x 150 ms are over
  TEST_ASSERT_FALSE(p.active());
  assertDuties(p, 0, 0, 0, 0);
}

void test_a_late_update_lands_on_the_right_step() {
  // If the loop is held up, the player must not fall behind step by step.
  PatternPlayer p;
  p.play(BLINK, 0);
  p.update(320);  // 320 = 2 rounds (300) + 20 ms into step 1 of round 3
  TEST_ASSERT_TRUE(p.active());
  assertDuties(p, 100, 0, 0, 0);
}

void test_a_new_pattern_replaces_the_one_playing() {
  PatternPlayer p;
  p.play(BLINK, 0);
  p.update(120);
  assertDuties(p, 0, 0, 0, 200);
  p.play(SOLID, 120);  // latest wins, starting from its own first step
  p.update(120);
  assertDuties(p, 50, 50, 50, 50);
  p.update(319);
  TEST_ASSERT_TRUE(p.active());
  p.update(320);
  TEST_ASSERT_FALSE(p.active());
}

void test_works_across_millis_wraparound() {
  // millis() wraps to 0 after about 49.7 days; start 16 ms before that.
  const uint32_t start = 0xFFFFFFF0u;
  PatternPlayer p;
  p.play(BLINK, start);
  p.update(start + 99);  // already past the wrap
  assertDuties(p, 100, 0, 0, 0);
  p.update(start + 100);
  assertDuties(p, 0, 0, 0, 200);
  p.update(start + 450);
  TEST_ASSERT_FALSE(p.active());
}

// --- built-in patterns ------------------------------------------------------

void test_built_in_patterns_are_playable() {
  // Every pattern in the table must have at least one step, one round, and no
  // zero-length step (which would never be felt).
  for (uint8_t id = 0; id < patterns::COUNT; id++) {
    const Pattern &pat = *patterns::ALL[id];
    TEST_ASSERT_TRUE(pat.numSteps >= 1);
    TEST_ASSERT_TRUE(pat.repeats >= 1);
    for (uint8_t s = 0; s < pat.numSteps; s++) TEST_ASSERT_TRUE(pat.steps[s].ms > 0);
  }
}

// --- override: pattern vs. the Jetson's strengths -----------------------------

static Frame setMotors(uint8_t m0, uint8_t m1, uint8_t m2, uint8_t m3) {
  Frame f{};
  f.type = MSG_SET_MOTORS;
  f.seq = 1;
  f.len = 4;
  f.payload[0] = m0;
  f.payload[1] = m1;
  f.payload[2] = m2;
  f.payload[3] = m3;
  return f;
}

void test_a_playing_pattern_overrides_the_jetson() {
  Controller c(1, 0, 3);
  uint8_t reply[MAX_FRAME];
  c.handleFrame(setMotors(0, 180, 180, 0), 0, reply);
  PatternPlayer p;
  p.play(SOLID, 0);
  p.update(10);
  for (uint8_t i = 0; i < 4; i++) TEST_ASSERT_EQUAL(50, outputDuty(p, c, i));
}

void test_the_jetson_takes_over_again_when_the_pattern_ends() {
  Controller c(1, 0, 3);
  uint8_t reply[MAX_FRAME];
  c.handleFrame(setMotors(0, 180, 180, 0), 0, reply);
  PatternPlayer p;
  p.play(SOLID, 0);
  p.update(200);  // SOLID is over
  c.tick(200);    // link still alive (last frame 200 ms ago)
  TEST_ASSERT_EQUAL(0, outputDuty(p, c, 0));
  TEST_ASSERT_EQUAL(180, outputDuty(p, c, 1));
  TEST_ASSERT_EQUAL(180, outputDuty(p, c, 2));
  TEST_ASSERT_EQUAL(0, outputDuty(p, c, 3));
}

void test_motors_stay_off_after_the_pattern_if_the_link_died_meanwhile() {
  Controller c(1, 0, 3);
  uint8_t reply[MAX_FRAME];
  c.handleFrame(setMotors(0, 180, 180, 0), 0, reply);
  PatternPlayer p;
  p.play(SOLID, 400);
  p.update(600);  // pattern over
  c.tick(600);    // 600 ms of silence: the watchdog zeroed the Jetson's strengths
  for (uint8_t i = 0; i < 4; i++) TEST_ASSERT_EQUAL(0, outputDuty(p, c, i));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_idle_at_start);
  RUN_TEST(test_play_starts_on_the_first_step);
  RUN_TEST(test_moves_to_the_next_step_exactly_when_its_time_is_up);
  RUN_TEST(test_repeats_the_right_number_of_times_then_stops);
  RUN_TEST(test_a_late_update_lands_on_the_right_step);
  RUN_TEST(test_a_new_pattern_replaces_the_one_playing);
  RUN_TEST(test_works_across_millis_wraparound);
  RUN_TEST(test_built_in_patterns_are_playable);
  RUN_TEST(test_a_playing_pattern_overrides_the_jetson);
  RUN_TEST(test_the_jetson_takes_over_again_when_the_pattern_ends);
  RUN_TEST(test_motors_stay_off_after_the_pattern_if_the_link_died_meanwhile);
  return UNITY_END();
}
