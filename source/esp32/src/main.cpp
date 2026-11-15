// Daredevil bracelet firmware: receive motor commands from the Jetson over
// Wi-Fi (UDP) or USB serial, drive the vibration motors with PWM, and fail safe
// (motors off) if the link goes quiet. Event patterns (boot, link lost, low
// battery, or requested with PLAY_PATTERN) override the Jetson while they play.
// The decisions live in the headers (controller, announcer, pattern_player,
// battery_monitor, output); this file only connects them to the hardware.

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>

#include "announcer.h"
#include "battery_monitor.h"
#include "config.h"
#include "controller.h"
#include "output.h"
#include "pattern_player.h"
#include "patterns.h"
#include "protocol.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Missing include/secrets.h: copy include/secrets.example.h to include/secrets.h and fill in the hotspot name and password"
#endif

static Controller controller(BRACELET_SIDE, FW_VERSION_MAJOR, FW_VERSION_MINOR);
static Announcer announcer(ANNOUNCE_PERIOD_MS, Controller::DEFAULT_LINK_TIMEOUT_MS);
static PatternPlayer player;
static BatteryMonitor battery(BATTERY_LOW_MV, BATTERY_CLEAR_MV);
static uint32_t lastBatteryCheckMs = 0;

// One parser per link: bytes from USB and Wi-Fi must never mix mid-frame.
static proto::Parser usbParser;
static proto::Parser wifiParser;

static WiFiUDP udp;
static bool udpOpen = false;
static const IPAddress JETSON_IP(JETSON_IP_OCTETS);

// --- motors ---------------------------------------------------------------

// arduino-esp32 3.x addresses PWM by pin; 2.x by channel.
static void motorsBegin() {
  for (uint8_t i = 0; i < proto::NUM_MOTORS; i++) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcAttach(MOTOR_PINS[i], MOTOR_PWM_FREQ_HZ, MOTOR_PWM_RESOLUTION_BITS);
#else
    ledcSetup(i, MOTOR_PWM_FREQ_HZ, MOTOR_PWM_RESOLUTION_BITS);
    ledcAttachPin(MOTOR_PINS[i], i);
#endif
  }
}

// Write what each motor should do now to the PWM outputs: a playing pattern,
// otherwise the Jetson's command (see output.h). Runs every loop, because a
// pattern changes with time; only pins whose value changed are written.
static void applyDuties() {
  static uint8_t written[proto::NUM_MOTORS];
  static bool anyWritten = false;
  for (uint8_t i = 0; i < proto::NUM_MOTORS; i++) {
    const uint8_t duty = outputDuty(player, controller, i);
    if (anyWritten && duty == written[i]) continue;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcWrite(MOTOR_PINS[i], duty);
#else
    ledcWrite(i, duty);
#endif
    written[i] = duty;
  }
  anyWritten = true;
}

static void playPattern(patterns::Id id, uint32_t now) { player.play(patterns::get(id), now); }

// --- battery --------------------------------------------------------------

static void serviceBattery(uint32_t now) {
  if (now - lastBatteryCheckMs < BATTERY_CHECK_MS) return;
  lastBatteryCheckMs = now;
  uint32_t sumMv = 0;
  for (uint8_t i = 0; i < BATTERY_SAMPLES; i++) sumMv += analogReadMilliVolts(BATTERY_PIN);
  const uint32_t batteryMv = sumMv / BATTERY_SAMPLES * BATTERY_DIVIDER;
  if (battery.update(static_cast<uint16_t>(batteryMv))) playPattern(patterns::LOW_BATTERY, now);
}

// --- links ----------------------------------------------------------------

static void serviceUsb(uint32_t now) {
  uint8_t reply[proto::MAX_FRAME];
  while (Serial.available() > 0) {
    if (!usbParser.feed((uint8_t)Serial.read())) continue;
    size_t n = controller.handleFrame(usbParser.frame, now, reply);
    Serial.write(reply, n);
  }
}

static void sendUdp(const IPAddress &ip, uint16_t port, const uint8_t *data, size_t len) {
  udp.beginPacket(ip, port);
  udp.write(data, len);
  udp.endPacket();
}

static void serviceWifi(uint32_t now) {
  // Open the UDP socket once Wi-Fi is up; drop it if the connection is lost
  // (auto-reconnect brings Wi-Fi back and this reopens it).
  bool connected = WiFi.status() == WL_CONNECTED;
  if (connected && !udpOpen) {
    udpOpen = udp.begin(UDP_PORT);
  } else if (!connected && udpOpen) {
    udp.stop();
    udpOpen = false;
  }
  if (!udpOpen) return;

  uint8_t packet[proto::MAX_FRAME];
  uint8_t reply[proto::MAX_FRAME];
  while (udp.parsePacket() > 0) {
    // Remember the sender before replying: beginPacket() overwrites remoteIP().
    IPAddress fromIp = udp.remoteIP();
    uint16_t fromPort = udp.remotePort();
    int len = udp.read(packet, sizeof(packet));  // bytes beyond one frame are dropped

    wifiParser.reset();  // one datagram = one frame
    for (int i = 0; i < len; i++) {
      if (!wifiParser.feed(packet[i])) continue;
      announcer.onLinkFrame(now);
      size_t n = controller.handleFrame(wifiParser.frame, now, reply);
      sendUdp(fromIp, fromPort, reply, n);
    }
  }

  if (announcer.shouldAnnounce(now)) {
    size_t n = controller.identityFrame(reply);
    sendUdp(JETSON_IP, UDP_PORT, reply, n);
  }
}

// --- main -----------------------------------------------------------------

void setup() {
  motorsBegin();
  applyDuties();  // all zero at boot

  Serial.begin(115200);  // baud is ignored on native USB
  // Don't block in Serial.write() when nothing reads the USB port -- that
  // would also stall the Wi-Fi link and the watchdog.
  Serial.setTxTimeoutMs(0);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // power saving can delay incoming commands by ~100 ms or more
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const uint32_t now = millis();
  playPattern(patterns::BOOT, now);
  lastBatteryCheckMs = now;  // first battery check 1 s from now, after the boot pattern
}

void loop() {
  uint32_t now = millis();
  serviceUsb(now);
  serviceWifi(now);

  uint8_t requested;
  if (controller.takePatternRequest(requested)) {
    playPattern(static_cast<patterns::Id>(requested), now);  // id already checked by the controller
  }
  if (controller.tick(now)) playPattern(patterns::LINK_LOST, now);  // watchdog fired
  serviceBattery(now);

  player.update(now);
  applyDuties();
}
