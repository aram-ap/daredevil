#!/usr/bin/env bash
# Runs ON THE JETSON (copied there by connect.sh). Picks a Python that can
# import pyrealsense2 (your project venv), then starts depth_stream.py.
#
# Override auto-detection with a venv path, absolute or relative to ~ :
#   REMOTE_VENV=daredevil/realsense-data-collection/.venv ./connect.sh user@jetson
cd "$(dirname "$0")"

find_python() {
  if [ -n "${REMOTE_VENV:-}" ]; then
    case "$REMOTE_VENV" in /*) v="$REMOTE_VENV" ;; *) v="$HOME/$REMOTE_VENV" ;; esac
    echo "$v/bin/python3"; return
  fi
  for v in "$HOME/daredevil/realsense-data-collection/.venv" "$HOME/daredevil/.venv" \
           "$HOME"/*/.venv "$HOME"/*/*/.venv; do
    if [ -x "$v/bin/python3" ] && "$v/bin/python3" -c "import pyrealsense2" 2>/dev/null; then
      echo "$v/bin/python3"; return
    fi
  done
  echo python3
}

PY="$(find_python)"
echo "Using Python: $PY"
exec "$PY" depth_stream.py "$@"
