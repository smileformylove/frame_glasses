import argparse
import asyncio
from pathlib import Path
import time

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
from voice_context import DEFAULT_CONTEXT_PATH, load_last_message, save_last_message
from voice_shortcuts import DEFAULT_SHORTCUTS_PATH, load_shortcuts
from voice_codex_core import (
    DEFAULT_COMMANDS,
    canceled_message,
    confirmation_prompt,
    execute_intent,
    build_follow_up_prompt,
    expired_message,
    locale_for_args,
    parse_intent,
    progress_message,
    requires_confirmation,
)


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
    parser.add_argument("--wake-word", default=None, help="Optional wake word such as codex or 眼镜; if set, only commands prefixed with it are acted on")
    parser.add_argument("--confirm-timeout", type=float, default=12.0, help="Seconds before a pending confirmation expires")
    parser.add_argument("--shortcuts-file", default=str(DEFAULT_SHORTCUTS_PATH), help="Path to custom voice shortcuts JSON")
    parser.add_argument("--context-file", default=str(DEFAULT_CONTEXT_PATH), help="Path to persisted voice result context JSON")
    return parser




def should_persist_result(message: str, should_exit: bool) -> bool:
    if should_exit or not message:
        return False
    blocked_prefixes = (
        "VOICE CODEX",
        "语音 Codex",
        "Confirm ",
        "确认执行：",
        "当前没有待确认操作。",
        "没有可重复的结果。",
        "还没有可追问的结果。",
    )
    return not any(message.startswith(prefix) for prefix in blocked_prefixes)


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


async def resolve_voice_intent(args, raw_text: str, pending_intent, pending_expires_at: float):
    locale = locale_for_args(args)
    shortcuts = load_shortcuts(Path(args.shortcuts_file).expanduser())
    intent = parse_intent(raw_text, wake_word=args.wake_word, shortcuts=shortcuts)
    confirmed = False

    if pending_intent is not None and time.monotonic() > pending_expires_at:
        if intent.action in ("confirm", "cancel"):
            return expired_message(locale), False, None, 0.0
        pending_intent = None
        pending_expires_at = 0.0

    if pending_intent is not None and intent.action == "ignored":
        intent = parse_intent(raw_text, wake_word=None, shortcuts=shortcuts)

    if pending_intent is not None:
        if intent.action == "confirm":
            intent = pending_intent
            pending_intent = None
            pending_expires_at = 0.0
            confirmed = True
        elif intent.action == "cancel":
            return canceled_message(locale), False, None, 0.0
        else:
            pending_intent = None
            pending_expires_at = 0.0

    if requires_confirmation(intent) and not confirmed:
        return confirmation_prompt(intent, locale), False, intent, time.monotonic() + args.confirm_timeout

    progress = progress_message(intent, locale) if requires_confirmation(intent) and confirmed else ""
    message, should_exit = await execute_intent(args, intent)
    if progress and not args.dry_run:
        await ResultDisplay(args).show(progress)
    return message, should_exit, pending_intent, pending_expires_at


def compact_for_args(args, text: str) -> str:
    return compact_text(text, args.limit)


async def run_demo(args) -> None:
    display = ResultDisplay(args)
    args.compact_text = lambda text: compact_for_args(args, text)
    commands = [part.strip() for part in args.demo_commands.split("|") if part.strip()]
    shortcuts = load_shortcuts(Path(args.shortcuts_file).expanduser())
    pending_intent = None
    pending_expires_at = 0.0
    context_file = Path(args.context_file).expanduser()
    last_message = load_last_message(context_file, "voice-codex") or ""

    for command_text in commands:
        print(f"[voice-codex] heard={command_text}")
        try:
            message, should_exit, pending_intent, pending_expires_at = await resolve_voice_intent(
                args, command_text, pending_intent, pending_expires_at
            )
        except Exception as exc:
            message, should_exit = f"VOICE CODEX error: {exc}", False
        action = parse_intent(command_text, wake_word=args.wake_word, shortcuts=shortcuts).action
        if action == "repeat":
            message = last_message or ("VOICE CODEX nothing to repeat." if locale_for_args(args) == "en" else "没有可重复的结果。")
        elif action == "follow_up":
            if not last_message:
                message = "VOICE CODEX nothing to explain yet." if locale_for_args(args) == "en" else "还没有可追问的结果。"
            else:
                follow_intent = type("TmpIntent", (), {"action": "codex_exec", "payload": build_follow_up_prompt(last_message, locale_for_args(args))})()
                message, should_exit = await execute_intent(args, follow_intent)
        if not message:
            continue
        print(f"[voice-codex] result={message}")
        if should_persist_result(message, should_exit):
            last_message = message
            save_last_message(context_file, "voice-codex", message)
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
    shortcuts = load_shortcuts(Path(args.shortcuts_file).expanduser())
    pending_intent = None
    pending_expires_at = 0.0
    context_file = Path(args.context_file).expanduser()
    last_message = load_last_message(context_file, "voice-codex") or ""

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
        try:
            message, should_exit, pending_intent, pending_expires_at = await resolve_voice_intent(
                args, text, pending_intent, pending_expires_at
            )
        except Exception as exc:
            message, should_exit = f"VOICE CODEX error: {exc}", False
        action = parse_intent(text, wake_word=args.wake_word, shortcuts=shortcuts).action
        if action == "repeat":
            message = last_message or ("VOICE CODEX nothing to repeat." if locale_for_args(args) == "en" else "没有可重复的结果。")
        elif action == "follow_up":
            if not last_message:
                message = "VOICE CODEX nothing to explain yet." if locale_for_args(args) == "en" else "还没有可追问的结果。"
            else:
                follow_intent = type("TmpIntent", (), {"action": "codex_exec", "payload": build_follow_up_prompt(last_message, locale_for_args(args))})()
                message, should_exit = await execute_intent(args, follow_intent)
        if not message:
            continue
        print(f"[voice-codex] result={message}")
        if should_persist_result(message, should_exit):
            last_message = message
            save_last_message(context_file, "voice-codex", message)
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
