import argparse
import asyncio
import time
from pathlib import Path

from frame_msg import FrameMsg, RxAudio

from frame_audio_gate import AdaptiveRmsGate
from frame_audio_profile import DEFAULT_PROFILE_PATH, load_profile
from frame_audio_utils import compute_rms, pcm_bytes_to_float32, preprocess_for_whisper
from frame_utils import display_kwargs_for_priority, paginate_text
from frame_mic_live_hud import append_log, choose_demo_lines, send_status_text, upload_runtime
from meeting_hud import FasterWhisperTranscriber
from speech_output import maybe_speak_result
from vision_hud import connect_frame_msg
from voice_context import DEFAULT_CONTEXT_PATH, load_last_message, save_last_message
from voice_task_state import DEFAULT_TASK_STATE_PATH
from voice_history import DEFAULT_HISTORY_PATH, append_history
from voice_shortcuts import DEFAULT_SHORTCUTS_PATH, load_shortcuts
from weather_profile import DEFAULT_WEATHER_PROFILE_PATH, load_weather_profile
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
    resolve_codex_bin,
)


DEFAULT_DEMO_COMMANDS = DEFAULT_COMMANDS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Use the Frame microphone to drive Codex and local developer workflows")
    parser.add_argument("--name", help="Optional BLE device name such as 'Frame EF'", default=None)
    parser.add_argument("--repo", default=".", help="Repo root used for local commands and Codex exec")
    parser.add_argument("--prefix", default="VOICE", help="Display prefix for transcript feedback")
    parser.add_argument("--dry-run", action="store_true", help="Do not run commands; only print what would happen")
    parser.add_argument("--render-mode", choices=("auto", "plain", "unicode"), default="auto", help="Result rendering mode on Frame")
    parser.add_argument("--visual-broadcast", action="store_true", help="Use a screen-first preset: unicode, large/high-priority display, and paged long results")
    parser.add_argument("--font-family", default=None, help="Optional font path for unicode rendering")
    parser.add_argument("--font-size", type=int, default=28, help="Unicode result font size")
    parser.add_argument("--display-width", type=int, default=600, help="Unicode result layout width")
    parser.add_argument("--max-rows", type=int, default=3, help="Maximum unicode result rows")
    parser.add_argument("--x", type=int, default=1, help="Display x coordinate")
    parser.add_argument("--y", type=int, default=1, help="Display y coordinate")
    parser.add_argument("--limit", type=int, default=100, help="Maximum plain-text result length")
    parser.add_argument("--window-duration", type=float, default=3.5, help="Seconds per transcription window")
    parser.add_argument("--overlap-duration", type=float, default=0.5, help="Seconds of overlap between windows")
    parser.add_argument("--sample-rate", type=int, default=8000, help="Frame audio sample rate")
    parser.add_argument("--min-rms", type=float, default=0.008, help="Silence threshold for normalized PCM windows")
    parser.add_argument("--trim-leading", type=float, default=0.25, help="Seconds trimmed from the start of each transcription window before Whisper preprocessing")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE_PATH), help="Path to the saved audio profile store")
    parser.add_argument("--use-profile", action="store_true", help="Load per-device audio settings from the profile store")
    parser.add_argument("--adaptive-rms", action="store_true", help="Use an adaptive noise gate instead of only relying on a fixed min RMS")
    parser.add_argument("--adaptive-alpha", type=float, default=0.9, help="EMA smoothing factor for the adaptive noise floor")
    parser.add_argument("--adaptive-multiplier", type=float, default=2.5, help="Multiplier applied to the estimated noise floor")
    parser.add_argument("--adaptive-bias", type=float, default=0.001, help="Small additive bias used by the adaptive gate")
    parser.add_argument("--model", default="base", help="faster-whisper model name")
    parser.add_argument("--language", default=None, help="Optional spoken language code such as en or zh")
    parser.add_argument("--device", default="auto", help="Whisper device, usually auto or cpu on macOS")
    parser.add_argument("--compute-type", default="int8", help="Whisper compute type")
    parser.add_argument("--beam-size", type=int, default=1, help="Whisper beam size")
    parser.add_argument("--test-command", default="pytest -q", help="Shell command used for the 'run tests' action")
    parser.add_argument("--weather-profile", default=str(DEFAULT_WEATHER_PROFILE_PATH), help="Path to persisted weather preferences JSON")
    parser.add_argument("--codex-bin", default="codex", help="Path to the Codex CLI executable")
    parser.add_argument("--default-weather-location", default=None, help="Default location used for weather queries without an explicit place")
    parser.add_argument("--codex-sandbox", default="workspace-write", help="Sandbox mode used for codex exec")
    parser.add_argument("--codex-full-auto", action="store_true", help="Pass --full-auto to codex exec")
    parser.add_argument("--codex-ephemeral", action="store_true", help="Pass --ephemeral to codex exec")
    parser.add_argument("--log-file", default=None, help="Optional transcript/result log file path")
    parser.add_argument("--reconnect", action="store_true", help="Automatically restart the live session if Frame disconnects or the stream ends unexpectedly")
    parser.add_argument("--max-restarts", type=int, default=0, help="Maximum reconnect attempts, 0 means unlimited")
    parser.add_argument("--restart-delay", type=float, default=2.0, help="Seconds to wait before reconnecting")
    parser.add_argument("--demo", action="store_true", help="Run a local demo without using the Frame microphone")
    parser.add_argument("--demo-commands", default=DEFAULT_DEMO_COMMANDS, help="Pipe-separated command phrases used in demo mode")
    parser.add_argument("--wake-word", default=None, help="Optional wake word such as codex or 眼镜; if set, only commands prefixed with it are acted on")
    parser.add_argument("--confirm-timeout", type=float, default=12.0, help="Seconds before a pending confirmation expires")
    parser.add_argument("--page-results", action="store_true", help="Split long results into multiple pages on the glasses")
    parser.add_argument("--page-max-chars", type=int, default=90, help="Maximum characters per page when paginating results")
    parser.add_argument("--page-delay", type=float, default=1.2, help="Seconds to wait between result pages")
    parser.add_argument("--announce-high-priority", action="store_true", help="Show important results in larger text on the glasses")
    parser.add_argument("--speak-results", action="store_true", help="Speak results aloud using macOS say on the Mac mini")
    parser.add_argument("--speak-policy", choices=("off", "important", "all"), default="off", help="Speech policy for macOS say: off, only important results, or all results")
    parser.add_argument("--say-voice", default=None, help="Optional macOS voice name used by say")
    parser.add_argument("--say-rate", type=int, default=None, help="Optional speech rate for macOS say")
    parser.add_argument("--shortcuts-file", default=str(DEFAULT_SHORTCUTS_PATH), help="Path to custom voice shortcuts JSON")
    parser.add_argument("--context-file", default=str(DEFAULT_CONTEXT_PATH), help="Path to persisted voice result context JSON")
    parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_PATH), help="Path to persisted voice history JSON")
    parser.add_argument("--task-state-file", default=str(DEFAULT_TASK_STATE_PATH), help="Path to persisted current-task state JSON")
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




def apply_visual_broadcast_preset(args) -> None:
    if not args.visual_broadcast:
        return
    args.render_mode = 'unicode'
    args.announce_high_priority = True
    args.page_results = True
    args.page_max_chars = min(getattr(args, 'page_max_chars', 90), 28)
    args.page_delay = max(getattr(args, 'page_delay', 1.2), 1.4)
    args.font_size = max(getattr(args, 'font_size', 28), 40)
    args.display_width = min(getattr(args, 'display_width', 600), 520)
    args.max_rows = min(getattr(args, 'max_rows', 3), 2)


def preflight_runtime(args) -> None:
    try:
        import faster_whisper  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency: faster-whisper. Install it with: pip install -r requirements-meeting.txt"
        ) from exc

    if not args.dry_run:
        args.codex_bin = resolve_codex_bin(args)


def apply_audio_profile(args) -> None:
    if not args.use_profile:
        return
    profile = load_profile(Path(args.profile).expanduser(), args.name)
    if not profile:
        return
    args.min_rms = float(profile.get('min_rms', args.min_rms))
    args.trim_leading = float(profile.get('trim_leading', args.trim_leading))
    if profile.get('sample_rate'):
        args.sample_rate = int(profile['sample_rate'])
    if not args.language and profile.get('language'):
        args.language = profile['language']
    if profile.get('adaptive_rms') is not None:
        args.adaptive_rms = bool(profile.get('adaptive_rms')) or args.adaptive_rms
    else:
        args.adaptive_rms = True
    if profile.get('adaptive_alpha') is not None:
        args.adaptive_alpha = float(profile.get('adaptive_alpha'))
    if profile.get('adaptive_multiplier') is not None:
        args.adaptive_multiplier = float(profile.get('adaptive_multiplier'))
    if profile.get('adaptive_bias') is not None:
        args.adaptive_bias = float(profile.get('adaptive_bias'))
    print(f"[{Path(__file__).stem}] loaded profile for {args.name}: min_rms={args.min_rms} trim_leading={args.trim_leading}")




def runtime_settings_summary(args) -> str:
    adaptive = 'on' if getattr(args, 'adaptive_rms', False) else 'off'
    return f"min_rms={args.min_rms:.4f} trim={args.trim_leading:.2f} adaptive={adaptive}"

def should_retry_exception(exc: Exception) -> bool:
    return not isinstance(exc, (ModuleNotFoundError, RuntimeError, ValueError))


def iter_result_pages(args, message: str):
    if not args.page_results:
        return [message]
    if len(message) <= args.page_max_chars and ' | ' not in message and ' ｜ ' not in message and '\n' not in message:
        return [message]
    return paginate_text(message, max_chars=args.page_max_chars, include_index=True)

def compact_for_args(args, text: str) -> str:
    from frame_utils import compact_text
    return compact_text(text, args.limit)


async def resolve_voice_intent(args, raw_text: str, pending_intent, pending_raw_text: str, pending_expires_at: float):
    locale = locale_for_args(args)
    shortcuts = load_shortcuts(Path(args.shortcuts_file).expanduser())
    intent = parse_intent(raw_text, wake_word=args.wake_word, shortcuts=shortcuts)
    confirmed = False
    confirmed_raw_text = raw_text

    if pending_intent is not None and time.monotonic() > pending_expires_at:
        if intent.action in ("confirm", "cancel"):
            return expired_message(locale), False, None, "", 0.0, "expired"
        pending_intent = None
        pending_raw_text = ""
        pending_expires_at = 0.0

    if pending_intent is not None and intent.action == "ignored":
        intent = parse_intent(raw_text, wake_word=None, shortcuts=shortcuts)

    if pending_intent is not None:
        if intent.action == "confirm":
            intent = pending_intent
            confirmed_raw_text = pending_raw_text or raw_text
            pending_intent = None
            pending_raw_text = ""
            pending_expires_at = 0.0
            confirmed = True
        elif intent.action == "cancel":
            return canceled_message(locale), False, None, "", 0.0, "cancel"
        else:
            pending_intent = None
            pending_raw_text = ""
            pending_expires_at = 0.0

    if requires_confirmation(intent) and not confirmed:
        return confirmation_prompt(intent, locale), False, intent, raw_text, time.monotonic() + args.confirm_timeout, intent.action

    progress = progress_message(intent, locale) if requires_confirmation(intent) and confirmed else ""
    message, should_exit = await execute_intent(args, intent)
    if progress:
        return f"{progress}\n{message}", should_exit, pending_intent, confirmed_raw_text if confirmed else pending_raw_text, pending_expires_at, intent.action
    return message, should_exit, pending_intent, confirmed_raw_text if confirmed else pending_raw_text, pending_expires_at, intent.action


async def run_demo(args) -> None:
    args.compact_text = lambda text: compact_for_args(args, text)
    commands = choose_demo_lines(args.demo_commands)
    shortcuts = load_shortcuts(Path(args.shortcuts_file).expanduser())
    pending_intent = None
    pending_raw_text = ""
    pending_expires_at = 0.0
    context_file = Path(args.context_file).expanduser()
    last_message = load_last_message(context_file, "frame-mic-codex") or ""
    for command_text in commands:
        print(f"[frame-mic-codex] heard={command_text}")
        try:
            message, should_exit, pending_intent, pending_raw_text, pending_expires_at, effective_action = await resolve_voice_intent(
                args, command_text, pending_intent, pending_raw_text, pending_expires_at
            )
        except Exception as exc:
            message, should_exit, effective_action = f"VOICE CODEX error: {exc}", False, "error"
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
        print(f"[frame-mic-codex] result={message}")
        if should_persist_result(message, should_exit):
            last_message = message
            save_last_message(context_file, "frame-mic-codex", message)
            history_heard = pending_raw_text or command_text
            append_history(Path(args.history_file).expanduser(), {"bridge": "frame-mic-codex", "heard": history_heard, "action": effective_action, "result": message})
            if pending_intent is None:
                pending_raw_text = ""
        pages = iter_result_pages(args, message)
        for idx, page in enumerate(pages):
            await send_status_text(None, page, args, unicode_mode=True)
            if idx < len(pages) - 1:
                await asyncio.sleep(args.page_delay)
        await maybe_speak_result(args, message, should_exit=should_exit)
        if should_exit:
            break


async def run_live_once(args) -> None:
    log_file = Path(args.log_file).expanduser() if args.log_file else None
    transcriber = FasterWhisperTranscriber(
        model_name=args.model,
        language=args.language,
        device=args.device,
        compute_type=args.compute_type,
        beam_size=args.beam_size,
        task="transcribe",
    )

    frame = FrameMsg()
    audio = RxAudio(streaming=True)
    queue = None
    pcm_buffer = bytearray()
    bytes_per_second = args.sample_rate * 2
    window_bytes = max(2, int(args.window_duration * bytes_per_second))
    step_seconds = max(0.1, args.window_duration - args.overlap_duration)
    step_bytes = max(2, int(step_seconds * bytes_per_second))
    last_heard = ""
    unicode_mode = True
    args.compact_text = lambda text: compact_for_args(args, text)
    shortcuts = load_shortcuts(Path(args.shortcuts_file).expanduser())
    pending_intent = None
    pending_raw_text = ""
    pending_expires_at = 0.0
    context_file = Path(args.context_file).expanduser()
    last_message = load_last_message(context_file, "frame-mic-codex") or ""
    rms_gate = AdaptiveRmsGate(args.min_rms, alpha=args.adaptive_alpha, multiplier=args.adaptive_multiplier, bias=args.adaptive_bias) if args.adaptive_rms else None

    settings = runtime_settings_summary(args)
    print(f"[frame-mic-codex] settings={settings}")
    await connect_frame_msg(frame, args.name)
    try:
        queue = await audio.attach(frame)
        await upload_runtime(frame)
        await send_status_text(frame, f"VOICE CODEX ready. Say help, doctor, run tests, ask codex, or exit.\n{settings}", args, unicode_mode)

        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            pcm_buffer.extend(chunk)

            while len(pcm_buffer) >= window_bytes:
                window = bytes(pcm_buffer[:window_bytes])
                del pcm_buffer[:step_bytes]

                samples = pcm_bytes_to_float32(window)
                rms = compute_rms(samples)
                if rms_gate is not None:
                    threshold = rms_gate.threshold()
                    print(f"[frame-mic-codex] rms={rms:.4f} threshold={threshold:.4f} noise_floor={rms_gate.noise_floor}")
                    voiced = rms_gate.should_transcribe(rms)
                    rms_gate.observe(rms, voiced=voiced)
                    if not voiced:
                        continue
                else:
                    print(f"[frame-mic-codex] rms={rms:.4f}")
                    if rms < args.min_rms:
                        continue

                whisper_audio = preprocess_for_whisper(samples, args.sample_rate, trim_leading_seconds=args.trim_leading)
                heard = await asyncio.to_thread(transcriber.transcribe, whisper_audio)
                if not heard or heard == last_heard:
                    continue
                last_heard = heard
                append_log(log_file, f"heard: {heard}")
                print(f"[frame-mic-codex] heard={heard}")

                try:
                    message, should_exit, pending_intent, pending_raw_text, pending_expires_at, effective_action = await resolve_voice_intent(
                        args, heard, pending_intent, pending_raw_text, pending_expires_at
                    )
                except Exception as exc:
                    message, should_exit, effective_action = f"VOICE CODEX error: {exc}", False, "error"
                action = parse_intent(heard, wake_word=args.wake_word, shortcuts=shortcuts).action
                if action == "repeat":
                    message = last_message or ("VOICE CODEX nothing to repeat." if locale_for_args(args) == "en" else "没有可重复的结果。")
                elif action == "follow_up":
                    if not last_message:
                        message = "VOICE CODEX nothing to explain yet." if locale_for_args(args) == "en" else "还没有可追问的结果。"
                    else:
                        follow_intent = type("TmpIntent", (), {"action": "codex_exec", "payload": build_follow_up_prompt(last_message, locale_for_args(args))})()
                        message, should_exit = await execute_intent(args, follow_intent)
                append_log(log_file, f"result: {message}")
                if not message:
                    continue
                print(f"[frame-mic-codex] result={message}")
                if pending_intent is None and not should_exit and action not in ("repeat", "confirm", "cancel", "help", "ignored", "exit"):
                    last_message = message
                    save_last_message(context_file, "frame-mic-codex", message)
                    history_heard = pending_raw_text or heard
                    append_history(Path(args.history_file).expanduser(), {"bridge": "frame-mic-codex", "heard": history_heard, "action": effective_action, "result": message})
                    pending_raw_text = ""
                pages = iter_result_pages(args, message)
                if args.announce_high_priority and (should_exit or ("CODEX" in message) or ("测试" in message)):
                    original = (args.font_size, args.display_width, args.max_rows)
                    overrides = display_kwargs_for_priority("high", args.font_size, args.display_width, args.max_rows)
                    args.font_size, args.display_width, args.max_rows = overrides["font_size"], overrides["display_width"], overrides["max_rows"]
                    for idx, page in enumerate(pages):
                        await send_status_text(frame, page, args, unicode_mode)
                        if idx < len(pages) - 1:
                            await asyncio.sleep(args.page_delay)
                    args.font_size, args.display_width, args.max_rows = original
                else:
                    for idx, page in enumerate(pages):
                        await send_status_text(frame, page, args, unicode_mode)
                        if idx < len(pages) - 1:
                            await asyncio.sleep(args.page_delay)
                await maybe_speak_result(args, message, should_exit=should_exit)
                if should_exit:
                    return
    finally:
        if queue is not None:
            audio.detach(frame)
        try:
            await frame.stop_frame_app(reset=True)
        except Exception:
            pass
        if frame.is_connected():
            await frame.disconnect()


async def async_main() -> None:
    args = build_parser().parse_args()
    profile = load_weather_profile(Path(args.weather_profile).expanduser())
    if not args.default_weather_location and profile.get("default_weather_location"):
        args.default_weather_location = profile.get("default_weather_location")
    apply_visual_broadcast_preset(args)
    if args.demo:
        await run_demo(args)
        return
    apply_audio_profile(args)
    preflight_runtime(args)
    restart_count = 0
    while True:
        try:
            await run_live_once(args)
            return
        except Exception as exc:
            if not args.reconnect or not should_retry_exception(exc):
                raise
            restart_count += 1
            print(f"[frame-mic-codex] reconnect attempt {restart_count}: {exc!r}")
            if args.max_restarts and restart_count > args.max_restarts:
                raise
            await asyncio.sleep(args.restart_delay)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nFrame Mic Codex Bridge stopped.")


if __name__ == "__main__":
    main()
