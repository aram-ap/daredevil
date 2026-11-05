#!/usr/bin/env bash
# Laptop-side launcher: copies the scripts to the Jetson, starts the stream there,
# forwards the port over SSH, and opens the live view once it is actually up.
#
#   ./connect.sh user@jetson-ip                       # default port 8085
#   ./connect.sh user@jetson-ip 8086 --filter --scheme 6
#   REMOTE_VENV=daredevil/realsense-data-collection/.venv ./connect.sh user@jetson-ip
#
# Extra args after the port go straight to depth_stream.py.
# You type your SSH password once (the connection is shared for the whole run).
# Ctrl+C stops the stream on the Jetson, releases the camera, closes the tunnel.
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $0 user@jetson-host [port] [depth_stream.py options...]" >&2
  exit 1
fi

HOST="$1"; shift
PORT="${1:-8085}"; [ $# -gt 0 ] && shift
EXTRA="$*"
HERE="$(cd "$(dirname "$0")" && pwd)"
REMOTE_DIR="depth_heatmap_live"   # relative to the Jetson home directory

# Share one SSH connection so the password is asked only once.
SSH_OPTS=(-o ControlMaster=auto -o "ControlPath=/tmp/dd-heatmap-$(id -u)-%C" -o ControlPersist=300)
trap 'ssh "${SSH_OPTS[@]}" -O exit "$HOST" >/dev/null 2>&1 || true' EXIT

echo "Connecting to $HOST and copying files ..."
ssh "${SSH_OPTS[@]}" "$HOST" "mkdir -p $REMOTE_DIR"
scp -q "${SSH_OPTS[@]}" "$HERE/depth_stream.py" "$HERE/launch.sh" "$HOST:$REMOTE_DIR/"

# Open the browser only after the stream answers (not after a fixed delay).
( for _ in $(seq 1 120); do
    if curl -sf -o /dev/null "http://localhost:$PORT/"; then
      URL="http://localhost:$PORT"
      if command -v open >/dev/null; then open "$URL"
      elif command -v xdg-open >/dev/null; then xdg-open "$URL"
      else echo "Open $URL in your browser"; fi
      exit 0
    fi
    sleep 0.5
  done ) &

REMOTE_ENV=""
if [ -n "${REMOTE_VENV:-}" ]; then REMOTE_ENV="REMOTE_VENV=$(printf '%q' "$REMOTE_VENV") "; fi

echo "Starting stream (Ctrl+C to stop) ..."
# -t lets Ctrl+C reach the remote python so it releases the camera.
ssh -t "${SSH_OPTS[@]}" -o ExitOnForwardFailure=yes -L "$PORT:localhost:$PORT" "$HOST" \
  "${REMOTE_ENV}bash $REMOTE_DIR/launch.sh --port $PORT $EXTRA"
