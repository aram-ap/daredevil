#pragma once

#include <stdint.h>

#include "protocol.h"

#ifndef BRACELET_SIDE
#error "BRACELET_SIDE must be set by the build (0 = left, 1 = right); see platformio.ini"
#endif

// 0.2: adds Wi-Fi with unsolicited IDENTITY announcements.
#define FW_VERSION_MAJOR 0
#define FW_VERSION_MINOR 2

// PLACEHOLDER pin map -- update once the bracelet PCB / motor driver is final.
// XIAO D1, D2, D3, D10 = GPIO 3, 4, 5, 10. Strapping pins GPIO 2, 8, 9
// (D0, D8, D9) are avoided so a motor circuit can't upset boot.
// PLACEHOLDER order: 0 = outer, 1 & 2 = inner pair, 3 = TBD.
static const uint8_t MOTOR_PINS[proto::NUM_MOTORS] = {3, 4, 5, 10};

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
