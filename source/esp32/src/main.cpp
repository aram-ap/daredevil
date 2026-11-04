// Daredevil bracelet firmware: receive motor commands from the Jetson over
// Wi-Fi (UDP) or USB serial, drive the vibration motors with PWM, and fail safe
// (motors off) if the link goes quiet. The decisions live in controller.h and
// announcer.h; this file only connects them to the hardware.

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>

#include "announcer.h"
#include "config.h"
#include "controller.h"
#include "protocol.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Missing include/secrets.h: copy include/secrets.example.h to include/secrets.h and fill in the hotspot name and password"
#endif

static Controller controller(BRACELET_SIDE, FW_VERSION_MAJOR, FW_VERSION_MINOR);
static Announcer announcer(ANNOUNCE_PERIOD_MS, Controller::DEFAULT_LINK_TIMEOUT_MS);

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

// Write the controller's duties to the PWM outputs.
static void applyDuties() {
  for (uint8_t i = 0; i < proto::NUM_MOTORS; i++) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcWrite(MOTOR_PINS[i], controller.duty(i));
#else
    ledcWrite(i, controller.duty(i));
#endif
  }
}

// --- links ----------------------------------------------------------------

static void serviceUsb(uint32_t now) {
  uint8_t reply[proto::MAX_FRAME];
  while (Serial.available() > 0) {
    if (!usbParser.feed((uint8_t)Serial.read())) continue;
    size_t n = controller.handleFrame(usbParser.frame, now, reply);
    applyDuties();
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
      applyDuties();
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
}

void loop() {
  uint32_t now = millis();
  serviceUsb(now);
  serviceWifi(now);
  if (controller.tick(now)) applyDuties();
}
