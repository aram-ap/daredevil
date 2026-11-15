#pragma once

#include <stdint.h>

#include "protocol.h"

#ifndef BRACELET_SIDE
#error "BRACELET_SIDE must be set by the build (0 = left, 1 = right); see platformio.ini"
#endif

// 0.2: adds Wi-Fi with unsolicited IDENTITY announcements.
// 0.3: adds event vibration patterns, PLAY_PATTERN and battery monitoring.
#define FW_VERSION_MAJOR 0
#define FW_VERSION_MINOR 3

// Motor pins from the wrist-module PCB (hardware/wrist_module, Rev A), which
// switches each motor through a ULN2003A:
//   motor 0 = MOT 1 = D1  = GPIO 3
//   motor 1 = MOT 2 = D2  = GPIO 4
//   motor 2 = MOT 3 = D5  = GPIO 7
//   motor 3 = MOT 4 = D10 = GPIO 10
//   (MOT 5 = D7 = GPIO 20 is on the PCB but unused while NUM_MOTORS is 4.)
// PLACEHOLDER: where each motor sits on the wrist is not decided yet.
static const uint8_t MOTOR_PINS[proto::NUM_MOTORS] = {3, 4, 7, 10};

// 20 kHz is above hearing, so the motors don't whine; 8 bits matches the
// 0..255 intensity byte in SET_MOTORS.
#define MOTOR_PWM_FREQ_HZ 20000
#define MOTOR_PWM_RESOLUTION_BITS 8

// Wi-Fi link. PLACEHOLDERS -- must match the Jetson hotspot and
// source/jetson/daredevil_link/udp.py. 10.42.0.1 is NetworkManager's usual
// address for the machine running a hotspot; check it on the Jetson.
#define JETSON_IP_OCTETS 10, 42, 0, 1
#define UDP_PORT 5005
#define ANNOUNCE_PERIOD_MS 1000

// Hotspot name and password live in secrets.h, which git ignores.

// Battery sense: the PCB's 100k/100k divider (R6/R7) feeds half the battery
// voltage to D0 (GPIO 2). GPIO 2 is a strapping pin; the divider holds it at
// about 2 V, which reads as "high" at reset, the normal boot setting.
#define BATTERY_PIN 2
#define BATTERY_DIVIDER 2     // battery mV = pin mV x 2
#define BATTERY_SAMPLES 8     // readings averaged per check (the ADC is noisy)
#define BATTERY_CHECK_MS 1000
// PLACEHOLDERS -- measure on the real battery. Low below LOW, re-armed at or
// above CLEAR (see battery_monitor.h).
#define BATTERY_LOW_MV 3500
#define BATTERY_CLEAR_MV 3700
