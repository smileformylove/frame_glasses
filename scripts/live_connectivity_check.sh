#!/usr/bin/env bash
set -euo pipefail

NAME=""
TEXT="live-check"
MIC_DURATION=3

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)
      NAME="$2"
      shift 2
      ;;
    --text)
      TEXT="$2"
      shift 2
      ;;
    --mic-duration)
      MIC_DURATION="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: ./scripts/live_connectivity_check.sh --name \"Frame EF\" [--text probe] [--mic-duration 3]" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$NAME" ]]; then
  echo "--name is required" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[live-check] 1/3 probe"
./scripts/run_frame_lab.sh probe -- --name "$NAME" --send-text "$TEXT"

echo "[live-check] 2/3 send text"
./scripts/run_frame_lab.sh say -- --name "$NAME" --text "$TEXT" --verbose

echo "[live-check] 3/3 frame mic test"
./scripts/run_frame_lab.sh frame-mic -- --name "$NAME" --duration "$MIC_DURATION"

echo "[live-check] done"
