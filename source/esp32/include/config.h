#pragma once

#include <stdint.h>

#ifndef BRACELET_SIDE
#error "BRACELET_SIDE must be set by the build (0 = left, 1 = right); see platformio.ini"
#endif

#define FW_VERSION_MAJOR 0
#define FW_VERSION_MINOR 1

// PLACEHOLDER pin map -- update once the bracelet PCB / motor driver is final.
// XIAO D1, D2, D3, D10 = GPIO 3, 4, 5, 10. Strapping pins GPIO 2, 8, 9
// (D0, D8, D9) are avoided so a motor circuit can't upset boot.
// PLACEHOLDER order: 0 = outer, 1 & 2 = inner pair, 3 = TBD.
#define NUM_MOTORS 4
static const uint8_t MOTOR_PINS[NUM_MOTORS] = {3, 4, 5, 10};

// 20 kHz is above hearing, so the motors don't whine; 8 bits matches the
// 0..255 intensity byte in SET_MOTORS.
#define MOTOR_PWM_FREQ_HZ 20000
#define MOTOR_PWM_RESOLUTION_BITS 8

// No valid frame for this long -> all motors off.
#define LINK_TIMEOUT_MS 500
