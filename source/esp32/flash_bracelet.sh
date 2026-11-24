#!/usr/bin/env bash
# Flash one bracelet with the left or right firmware image, then check that it
# now reports the side you asked for.
#
# Usage (from anywhere):
#   source/esp32/flash_bracelet.sh right                            # finds the plugged-in XIAO itself
#   source/esp32/flash_bracelet.sh left /dev/cu.usbmodem14101        # or name the port
#
# Plug in ONE bracelet at a time. Only boards with Espressif's USB ID
# (303A:1001, the XIAO ESP32-C3) are picked, so the Jetson's USB port is skipped.
set -euo pipefail

side="${1:-}"
port="${2:-}"
if [[ "$side" != "left" && "$side" != "right" ]]; then
  echo "Usage: $0 left|right [usb-port]" >&2
  exit 2
fi

esp32_dir="$(cd "$(dirname "$0")" && pwd)"
jetson_dir="$esp32_dir/../jetson"

if [[ ! -f "$esp32_dir/include/secrets.h" ]]; then
  echo "Missing include/secrets.h (the hotspot name and password)." >&2
  echo "Copy include/secrets.example.h to include/secrets.h and fill it in first." >&2
  exit 1
fi

if [[ -z "$port" ]]; then
  # List USB serial devices and keep only XIAO ESP32-C3 boards. On a Mac each
  # board appears twice (/dev/cu.* and /dev/tty.*); keep the cu.* one.
  ports="$(pio device list --json-output | python3 -c '
import json, sys
for d in json.load(sys.stdin):
    if "303A:1001" in d.get("hwid", "").upper() and not d["port"].startswith("/dev/tty."):
        print(d["port"])
')"
  count="$(printf '%s' "$ports" | grep -c . || true)"
  if [[ "$count" -eq 0 ]]; then
    echo "No XIAO ESP32-C3 found on USB. Plug the bracelet in with a data USB-C cable and retry." >&2
    exit 1
  fi
  if [[ "$count" -gt 1 ]]; then
    echo "More than one XIAO is plugged in:" >&2
    echo "$ports" >&2
    echo "Unplug the others, or name the port: $0 $side <port>" >&2
    exit 1
  fi
  port="$ports"
fi

echo "Flashing the $side image to $port ..."
(cd "$esp32_dir" && pio run -e "$side" -t upload --upload-port "$port")

echo "Waiting for the bracelet to restart ..."
sleep 3

python="$jetson_dir/.venv/bin/python"
[[ -x "$python" ]] || python="python3"
echo "Checking that it now says $side ..."
cd "$jetson_dir"
"$python" -m examples.check_bracelets --port "$port" --expect "$side"
