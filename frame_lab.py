import argparse
import subprocess
import sys
from pathlib import Path


COMMANDS = {
    "scan": "examples/scan_frame.py",
    "pair-test": "examples/pair_and_test.py",
    "say": "examples/send_text.py",
    "stdin-hud": "examples/stdin_hud.py",
    "run-hud": "examples/run_with_hud.py",
    "meeting": "examples/meeting_hud.py",
    "vision": "examples/vision_hud.py",
    "tap-vision": "examples/tap_vision_hud.py",
    "memory": "examples/memory_hud.py",
    "tap-memory": "examples/tap_memory_hud.py",
    "voice": "examples/voice_command_hud.py",
    "doctor": "examples/doctor.py",
    "agent-hud": "examples/agent_hud.py",
    "notify-run": "examples/notify_run.py",
    "frame-mic": "examples/frame_mic_test.py",
    "frame-mic-live": "examples/frame_mic_live_hud.py",
}

DESCRIPTIONS = {
    "scan": "Scan nearby Frame BLE devices",
    "pair-test": "Find the nearest Frame and send a test message",
    "say": "Send one line of text to Frame",
    "stdin-hud": "Mirror stdin lines to Frame",
    "run-hud": "Run a command and mirror useful output to Frame",
    "meeting": "Run meeting subtitle / translation / speaker HUD",
    "vision": "Capture or load an image, analyze it, and display the result",
    "tap-vision": "Tap the glasses to capture and analyze a scene",
    "memory": "Remember scenes and recall notes when seeing them again",
    "tap-memory": "Tap the glasses to recall or save scene memories",
    "voice": "Use voice commands to drive vision and memory workflows",
    "doctor": "Check whether the local environment is ready for Frame development",
    "agent-hud": "Run a persistent notification service and sender for Frame",
    "notify-run": "Run a command and send its status to Agent HUD",
    "frame-mic": "Record a short WAV clip from the Frame microphone",
    "frame-mic-live": "Stream and transcribe audio from the Frame microphone",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified launcher for the Frame on Mac mini starter",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("command", choices=COMMANDS.keys(), help=build_command_help())
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed through to the selected command")
    return parser


def build_command_help() -> str:
    lines = []
    for command in COMMANDS:
        lines.append(f"{command:<10} {DESCRIPTIONS[command]}")
    return "\n".join(lines)


def main() -> None:
    parser = build_parser()
    parsed = parser.parse_args()

    extra_args = parsed.args
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]

    script_path = Path(__file__).resolve().parent / COMMANDS[parsed.command]
    command = [sys.executable, str(script_path), *extra_args]
    raise SystemExit(subprocess.run(command).returncode)


if __name__ == "__main__":
    main()
