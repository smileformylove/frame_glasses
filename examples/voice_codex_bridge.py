import argparse
import asyncio
from pathlib import Path

from frame_utils import FrameUnicodeDisplay, compact_text
from meeting_hud import (
    FasterWhisperTranscriber,
    capture_audio_chunk,
    compute_rms,
    list_audio_devices,
    normalize_audio,
    parse_audio_device,
)
from vision_hud import choose_display
from voice_codex_core import DEFAULT_COMMANDS, DEFAULT_HELP_TEXT, execute_intent, parse_intent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Listen for voice commands and run safe local actions or Codex exec requests")
    parser.add_argument("--name", help="Optional BLE device name such as 'Frame EF'", default=None)
    parser.add_argument("--repo", default=".", help="Repo root used for local commands and Codex exec")
    parser.add_argument("--dry-run", action="store_true", help="Do not run commands; only print what would happen")
    parser.add_argument("--render-mode", choices=("auto", "plain", "unicode"), default="auto", help="Result rendering mode on Frame")
    parser.add_argument("--font-family", default=None, help="Optional font path for unicode rendering")
    parser.add_argument("--font-size", type=int, default=28, help="Unicode result font size")
    parser.add_argument("--display-width", type=int, default=600, help="Unicode result layout width")
    parser.add_argument("--max-rows", type=int, default=3, help="Maximum unicode result rows")
    parser.add_argument("--x", type=int, default=1, help="Display x coordinate")
    parser.add_argument("--y", type=int, default=1, help="Display y coordinate")
    parser.add_argument("--limit", type=int, default=100, help="Maximum plain-text result length")
    parser.add_argument("--list-devices", action="store_true", help="List audio input devices and exit")
    parser.add_argument("--audio-device", help="Audio device index or name", default=None)
    parser.add_argument("--listen-duration", type=float, default=3.0, help="Seconds recorded per voice command attempt")
    parser.add_argument("--samplerate", type=int, default=16000, help="Audio sample rate")
    parser.add_argument("--min-rms", type=float, default=0.015, help="Silence threshold for command audio")
    parser.add_argument("--model", default="base", help="faster-whisper model name")
    parser.add_argument("--language", default=None, help="Optional spoken command language code such as en or zh")
    parser.add_argument("--device", default="auto", help="Whisper device, usually auto or cpu on macOS")
    parser.add_argument("--compute-type", default="int8", help="Whisper compute type")
    parser.add_argument("--beam-size", type=int, default=1, help="Whisper beam size")
    parser.add_argument("--test-command", default="pytest -q", help="Shell command used for the 'run tests' voice action")
    parser.add_argument("--codex-bin", default="codex", help="Path to the Codex CLI executable")
    parser.add_argument("--codex-sandbox", default="workspace-write", help="Sandbox mode used for codex exec")
    parser.add_argument("--codex-full-auto", action="store_true", help="Pass --full-auto to codex exec")
    parser.add_argument("--codex-ephemeral", action="store_true", help="Pass --ephemeral to codex exec")
    parser.add_argument("--demo", action="store_true", help="Run a local demo without using the microphone")
    parser.add_argument("--demo-commands", default=DEFAULT_COMMANDS, help="Pipe-separated command phrases used in demo mode")
    return parser


class ResultDisplay:
    def __init__(self, args):
        self.args = args

    async def show(self, text: str) -> None:
        display = choose_display(self.args, text)
        rendered = text if isinstance(display, FrameUnicodeDisplay) else compact_text(text, self.args.limit)
        await display.connect()
        try:
            await display.show_text(rendered, x=self.args.x, y=self.args.y)
        finally:
            await display.disconnect()


def compact_for_args(args, text: str) -> str:
    return compact_text(text, args.limit)


async def run_demo(args) -> None:
    display = ResultDisplay(args)
    args.compact_text = lambda text: compact_for_args(args, text)
    commands = [part.strip() for part in args.demo_commands.split("|") if part.strip()]
    for command_text in commands:
        print(f"[voice-codex] heard={command_text}")
        intent = parse_intent(command_text)
        try:
            message, should_exit = await execute_intent(args, intent)
        except Exception as exc:
            message, should_exit = f"VOICE CODEX error: {exc}", False
        print(f"[voice-codex] result={message}")
        if not args.dry_run:
            await display.show(message)
        if should_exit:
            break


async def run_live(args) -> None:
    transcriber = FasterWhisperTranscriber(
        model_name=args.model,
        language=args.language,
        device=args.device,
        compute_type=args.compute_type,
        beam_size=args.beam_size,
        task="transcribe",
    )
    args.compact_text = lambda text: compact_for_args(args, text)
    display = ResultDisplay(args)
    await display.show("VOICE CODEX ready. Say help, doctor, scan, run tests, ask codex, or exit.")

    while True:
        audio_chunk = await asyncio.to_thread(capture_audio_chunk, args.listen_duration, args.samplerate, parse_audio_device(args.audio_device))
        rms = compute_rms(audio_chunk)
        print(f"[voice-codex] rms={rms:.4f}")
        if rms < args.min_rms:
            continue

        normalized = normalize_audio(audio_chunk)
        text = await asyncio.to_thread(transcriber.transcribe, normalized)
        if not text:
            continue

        print(f"[voice-codex] heard={text}")
        intent = parse_intent(text)
        try:
            message, should_exit = await execute_intent(args, intent)
        except Exception as exc:
            message, should_exit = f"VOICE CODEX error: {exc}", False
        print(f"[voice-codex] result={message}")
        await display.show(message)
        if should_exit:
            break


async def async_main() -> None:
    args = build_parser().parse_args()
    if args.list_devices:
        list_audio_devices()
        return
    if args.demo:
        await run_demo(args)
        return
    await run_live(args)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nVoice Codex Bridge stopped.")


if __name__ == "__main__":
    main()
