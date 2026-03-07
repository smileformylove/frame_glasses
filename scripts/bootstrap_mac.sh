#!/usr/bin/env bash
set -euo pipefail

MODE="full"
PYTHON_BIN="python3"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --minimal)
      MODE="minimal"
      shift
      ;;
    --full)
      MODE="full"
      shift
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: ./scripts/bootstrap_mac.sh [--minimal|--full] [--python python3]" >&2
      exit 1
      ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[bootstrap] repo: $ROOT_DIR"
echo "[bootstrap] mode: $MODE"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[bootstrap] error: python interpreter not found: $PYTHON_BIN" >&2
  exit 1
fi

if command -v xcode-select >/dev/null 2>&1; then
  if ! xcode-select -p >/dev/null 2>&1; then
    echo "[bootstrap] Xcode Command Line Tools not found. Run: xcode-select --install"
  else
    echo "[bootstrap] Xcode Command Line Tools: OK"
  fi
fi

if command -v brew >/dev/null 2>&1; then
  echo "[bootstrap] Installing/updating Homebrew packages"
  brew install portaudio ffmpeg tesseract
else
  echo "[bootstrap] Homebrew not found. Install it from https://brew.sh/ if you need audio/OCR tooling."
fi

if [[ ! -d .venv ]]; then
  echo "[bootstrap] Creating virtual environment"
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip

echo "[bootstrap] Installing base requirements"
pip install -r requirements.txt

if [[ "$MODE" == "full" ]]; then
  echo "[bootstrap] Installing optional requirements"
  pip install -r requirements-meeting.txt
  pip install -r requirements-translation.txt
  pip install -r requirements-speaker.txt
  pip install -r requirements-vision.txt
  pip install -r requirements-voice.txt
else
  echo "[bootstrap] Skipping optional requirements in minimal mode"
fi

echo "[bootstrap] Done"
echo "[bootstrap] Next steps:"
echo "  source .venv/bin/activate"
echo "  python frame_lab.py doctor"
echo "  python frame_lab.py pair-test -- --text \"Hello from Mac mini\""
