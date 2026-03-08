import argparse
import asyncio
from pathlib import Path

from frame_msg import FrameMsg, RxAudio

from frame_mic_live_hud import (
    append_log,
    choose_demo_lines,
    compute_rms,
    pcm_to_float32,
    send_status_text,
    upload_runtime,
)
from meeting_hud import FasterWhisperTranscriber
from vision_hud import connect_frame_msg
from voice_codex_core import DEFAULT_COMMANDS, execute_intent, parse_intent


DEFAULT_DEMO_COMMANDS = DEFAULT_COMMANDS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Use the Frame microphone to drive Codex and local developer workflows")
    parser.add_argument("--name", help="Optional BLE device name such as 'Frame EF'", default=None)
    parser.add_argument("--repo", default=".", help="Repo root used for local commands and Codex exec")
    parser.add_argument("--prefix", default="VOICE", help="Display prefix for transcript feedback")
    parser.add_argument("--dry-run", action="store_true", help="Do not run commands; only print what would happen")
    parser.add_argument("--render-mode", choices=("auto", "plain", "unicode"), default="auto", help="Result rendering mode on Frame")
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
    parser.add_argument("--model", default="base", help="faster-whisper model name")
    parser.add_argument("--language", default=None, help="Optional spoken language code such as en or zh")
    parser.add_argument("--device", default="auto", help="Whisper device, usually auto or cpu on macOS")
    parser.add_argument("--compute-type", default="int8", help="Whisper compute type")
    parser.add_argument("--beam-size", type=int, default=1, help="Whisper beam size")
    parser.add_argument("--test-command", default="pytest -q", help="Shell command used for the 'run tests' action")
    parser.add_argument("--codex-bin", default="codex", help="Path to the Codex CLI executable")
    parser.add_argument("--codex-sandbox", default="workspace-write", help="Sandbox mode used for codex exec")
    parser.add_argument("--codex-full-auto", action="store_true", help="Pass --full-auto to codex exec")
    parser.add_argument("--codex-ephemeral", action="store_true", help="Pass --ephemeral to codex exec")
    parser.add_argument("--log-file", default=None, help="Optional transcript/result log file path")
    parser.add_argument("--demo", action="store_true", help="Run a local demo without using the Frame microphone")
    parser.add_argument("--demo-commands", default=DEFAULT_DEMO_COMMANDS, help="Pipe-separated command phrases used in demo mode")
    return parser


def compact_for_args(args, text: str) -> str:
    from frame_utils import compact_text
    return compact_text(text, args.limit)


async def run_demo(args) -> None:
    args.compact_text = lambda text: compact_for_args(args, text)
    commands = choose_demo_lines(args.demo_commands)
    for command_text in commands:
        print(f"[frame-mic-codex] heard={command_text}")
        intent = parse_intent(command_text)
        try:
            message, should_exit = await execute_intent(args, intent)
        except Exception as exc:
            message, should_exit = f"VOICE CODEX error: {exc}", False
        print(f"[frame-mic-codex] result={message}")
        await send_status_text(None, message, args, unicode_mode=True)
        if should_exit:
            break


async def run_live(args) -> None:
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

    await connect_frame_msg(frame, args.name)
    try:
        queue = await audio.attach(frame)
        await upload_runtime(frame)
        await send_status_text(frame, "VOICE CODEX ready. Say help, doctor, run tests, ask codex, or exit.", args, unicode_mode)

        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            pcm_buffer.extend(chunk)

            while len(pcm_buffer) >= window_bytes:
                window = bytes(pcm_buffer[:window_bytes])
                del pcm_buffer[:step_bytes]

                samples = pcm_to_float32(window)
                rms = compute_rms(samples)
                print(f"[frame-mic-codex] rms={rms:.4f}")
                if rms < args.min_rms:
                    continue

                heard = await asyncio.to_thread(transcriber.transcribe, samples)
                if not heard or heard == last_heard:
                    continue
                last_heard = heard
                append_log(log_file, f"heard: {heard}")
                print(f"[frame-mic-codex] heard={heard}")

                intent = parse_intent(heard)
                try:
                    message, should_exit = await execute_intent(args, intent)
                except Exception as exc:
                    message, should_exit = f"VOICE CODEX error: {exc}", False
                append_log(log_file, f"result: {message}")
                print(f"[frame-mic-codex] result={message}")
                await send_status_text(frame, message, args, unicode_mode)
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
    if args.demo:
        await run_demo(args)
        return
    await run_live(args)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nFrame Mic Codex Bridge stopped.")


if __name__ == "__main__":
    main()
