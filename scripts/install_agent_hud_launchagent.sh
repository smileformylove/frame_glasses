#!/usr/bin/env bash
set -euo pipefail

ACTION="install"
DEVICE_NAME=""
PORT="8765"
HOST="127.0.0.1"
RENDER_MODE="unicode"
DRY_RUN="false"
LABEL="com.frameglasses.agenthud"

while [[ $# -gt 0 ]]; do
  case "$1" in
    install|uninstall|status)
      ACTION="$1"
      shift
      ;;
    --name)
      DEVICE_NAME="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --host)
      HOST="$2"
      shift 2
      ;;
    --render-mode)
      RENDER_MODE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: ./scripts/install_agent_hud_launchagent.sh [install|uninstall|status] [--name \"Frame 4F\"] [--port 8765] [--host 127.0.0.1] [--render-mode unicode] [--dry-run]" >&2
      exit 1
      ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$HOME/Library/Logs/frame_glasses"
STDOUT_LOG="$LOG_DIR/agent_hud.out.log"
STDERR_LOG="$LOG_DIR/agent_hud.err.log"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
FRAME_LAB="$ROOT_DIR/frame_lab.py"

mkdir -p "$LOG_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "python3 not found" >&2
  exit 1
fi

install_agent() {
  cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>${FRAME_LAB}</string>
    <string>agent-hud</string>
    <string>--</string>
    <string>serve</string>
    <string>--host</string>
    <string>${HOST}</string>
    <string>--port</string>
    <string>${PORT}</string>
    <string>--render-mode</string>
    <string>${RENDER_MODE}</string>
PLIST

  if [[ -n "$DEVICE_NAME" ]]; then
    cat >> "$PLIST_PATH" <<PLIST
    <string>--name</string>
    <string>${DEVICE_NAME}</string>
PLIST
  fi

  if [[ "$DRY_RUN" == "true" ]]; then
    cat >> "$PLIST_PATH" <<PLIST
    <string>--dry-run</string>
PLIST
  fi

  cat >> "$PLIST_PATH" <<PLIST
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${STDOUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${STDERR_LOG}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
</dict>
</plist>
PLIST

  launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
  launchctl load "$PLIST_PATH"
  echo "Installed LaunchAgent: $PLIST_PATH"
  echo "Logs: $STDOUT_LOG and $STDERR_LOG"
}

uninstall_agent() {
  launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
  rm -f "$PLIST_PATH"
  echo "Removed LaunchAgent: $PLIST_PATH"
}

status_agent() {
  if [[ -f "$PLIST_PATH" ]]; then
    echo "Plist exists: $PLIST_PATH"
    launchctl list | grep "$LABEL" || true
    echo "---"
    tail -n 20 "$STDOUT_LOG" 2>/dev/null || true
    echo "---"
    tail -n 20 "$STDERR_LOG" 2>/dev/null || true
  else
    echo "LaunchAgent not installed: $PLIST_PATH"
  fi
}

case "$ACTION" in
  install)
    install_agent
    ;;
  uninstall)
    uninstall_agent
    ;;
  status)
    status_agent
    ;;
esac
