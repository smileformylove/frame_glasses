#!/usr/bin/env bash
set -euo pipefail

URL="http://127.0.0.1:8765/notify"
PREFIX="LIVE"
LEVEL="info"
COUNT=20
INTERVAL=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)
      URL="$2"
      shift 2
      ;;
    --prefix)
      PREFIX="$2"
      shift 2
      ;;
    --level)
      LEVEL="$2"
      shift 2
      ;;
    --count)
      COUNT="$2"
      shift 2
      ;;
    --interval)
      INTERVAL="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: ./scripts/realtime_agent_hud_test.sh [--url URL] [--prefix LIVE] [--level info] [--count 20] [--interval 1]" >&2
      exit 1
      ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

for ((i=1; i<=COUNT; i++)); do
  NOW="$(date +%T)"
  "$PYTHON_BIN" "$ROOT_DIR/frame_lab.py" agent-hud -- send --url "$URL" --prefix "$PREFIX" --level "$LEVEL" --text "tick $i at $NOW"
  sleep "$INTERVAL"
done
