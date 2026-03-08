import argparse
import asyncio
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from frame_msg import FrameMsg, RxAudio

from frame_utils import build_unicode_payloads, compact_text, resolve_unicode_font
from meeting_hud import FasterWhisperTranscriber, build_display_text, build_translator, maybe_translate
from vision_hud import connect_frame_msg

PLAIN_TEXT_MSG_CODE = 0x21
UNICODE_TEXT_MSG_CODE = 0x20
DEFAULT_DEMO_LINES = (
    "frame mic live ready",
    "hello from the glasses microphone",
    "this is a realtime transcript running on mac mini",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stream audio from the Frame microphone to the Mac and display live transcripts on the glasses")
    parser.add_argument("--name", help="Optional BLE device name such as 'Frame 4F'", default=None)
    parser.add_argument("--prefix", default="MIC", help="Display prefix")
    parser.add_argument("--dry-run", action="store_true", help="Print transcripts locally instead of sending them back to Frame")
    parser.add_argument("--demo", action="store_true", help="Run a built-in transcript demo instead of using the Frame microphone")
    parser.add_argument("--demo-lines", default=None, help="Custom demo lines separated by |")
    parser.add_argument("--demo-delay", type=float, default=1.2, help="Delay between demo transcript lines")
    parser.add_argument("--render-mode", choices=("auto", "plain", "unicode"), default="auto", help="Transcript rendering mode")
    parser.add_argument("--font-family", default=None, help="Optional font path for unicode rendering")
    parser.add_argument("--font-size", type=int, default=28, help="Unicode transcript font size")
    parser.add_argument("--display-width", type=int, default=600, help="Unicode transcript layout width")
    parser.add_argument("--max-rows", type=int, default=3, help="Maximum unicode transcript rows")
    parser.add_argument("--limit", type=int, default=90, help="Maximum plain-text transcript length")
    parser.add_argument("--x", type=int, default=1, help="Display x coordinate")
    parser.add_argument("--y", type=int, default=1, help="Display y coordinate")
    parser.add_argument("--window-duration", type=float, default=3.0, help="Seconds per transcription window")
    parser.add_argument("--overlap-duration", type=float, default=0.5, help="Seconds of overlap between windows")
    parser.add_argument("--sample-rate", type=int, default=8000, help="Frame audio sample rate")
    parser.add_argument("--min-rms", type=float, default=0.01, help="Silence threshold for normalized PCM windows")
    parser.add_argument("--model", default="base", help="faster-whisper model name")
    parser.add_argument("--language", default=None, help="Optional spoken language code such as en or zh")
    parser.add_argument("--device", default="auto", help="Whisper device, usually auto or cpu on macOS")
    parser.add_argument("--compute-type", default="int8", help="Whisper compute type")
    parser.add_argument("--beam-size", type=int, default=1, help="Whisper beam size")
    parser.add_argument("--translate-to", default=None, help="Optional target language such as English or Chinese")
    parser.add_argument("--translation-provider", choices=("auto", "whisper", "openai"), default="auto", help="Translation backend")
    parser.add_argument("--bilingual", action="store_true", help="Show original and translated text together when supported")
    parser.add_argument("--log-file", default=None, help="Optional transcript log file path")
    parser.add_argument("--reconnect", action="store_true", help="Automatically restart the live session if Frame disconnects or the stream ends unexpectedly")
    parser.add_argument("--max-restarts", type=int, default=0, help="Maximum reconnect attempts, 0 means unlimited")
    parser.add_argument("--restart-delay", type=float, default=2.0, help="Seconds to wait before reconnecting")
    return parser




def preflight_runtime(args) -> None:
    try:
        import faster_whisper  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency: faster-whisper. Install it with: pip install -r requirements-meeting.txt"
        ) from exc

    if args.translate_to and args.translation_provider == "openai":
        try:
            import openai  # noqa: F401
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Missing dependency: openai. Install it with: pip install -r requirements-translation.txt"
            ) from exc


def should_retry_exception(exc: Exception) -> bool:
    return not isinstance(exc, (ModuleNotFoundError, RuntimeError, ValueError))

def choose_demo_lines(raw_lines: Optional[str]) -> Sequence[str]:
    if not raw_lines:
        return DEFAULT_DEMO_LINES
    lines = [part.strip() for part in raw_lines.split("|") if part.strip()]
    return lines or DEFAULT_DEMO_LINES


def choose_unicode_mode(args, sample_lines: Sequence[str]) -> bool:
    if args.render_mode == "unicode":
        return True
    if args.render_mode == "plain":
        return False
    if args.translate_to and any(keyword in args.translate_to.lower() for keyword in ("chinese", "中文", "zh", "japanese", "日文", "ja", "korean", "韩文", "ko")):
        return True
    if args.language and args.language.lower().startswith(("zh", "ja", "ko")):
        return True
    if any(any(ord(char) > 127 for char in line) for line in sample_lines):
        return True
    return resolve_unicode_font(args.font_family) is not None


async def upload_runtime(frame: FrameMsg) -> str:
    frame_app_name = "frame_stream_mic_frame_app"
    frame_app_path = Path(__file__).resolve().parent / "frame_apps" / f"{frame_app_name}.lua"
    await frame.upload_stdlua_libs(["data", "audio", "text_sprite_block"])
    await frame.upload_frame_app(str(frame_app_path), f"{frame_app_name}.lua")
    await frame.start_frame_app(frame_app_name, await_print=True)
    return frame_app_name


async def send_status_text(frame: FrameMsg, text: str, args, unicode_mode: bool) -> None:
    if args.dry_run:
        print(f"[frame-mic dry-run] {text}")
        return

    if unicode_mode:
        payloads = build_unicode_payloads(
            text=text,
            font_family=resolve_unicode_font(args.font_family),
            font_size=args.font_size,
            display_width=args.display_width,
            max_rows=args.max_rows,
            x=args.x,
            y=args.y,
        )
        for payload in payloads:
            await frame.send_message(UNICODE_TEXT_MSG_CODE, payload)
        return

    await frame.send_message(PLAIN_TEXT_MSG_CODE, compact_text(text, args.limit).encode("utf-8"))


def pcm_to_float32(pcm_bytes: bytes) -> np.ndarray:
    samples = np.frombuffer(pcm_bytes, dtype="<i2").astype(np.float32)
    return samples / 32768.0


def compute_rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))


def append_log(log_file: Optional[Path], line: str) -> None:
    if log_file is None:
        return
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


async def run_demo(args) -> None:
    lines = choose_demo_lines(args.demo_lines)
    unicode_mode = choose_unicode_mode(args, lines)
    for line in lines:
        print(f"[frame-mic] demo={line}")
        await send_status_text(None, f"{args.prefix} {line}".strip(), args, unicode_mode)
        await asyncio.sleep(args.demo_delay)


async def run_live_once(args) -> None:
    log_file = Path(args.log_file).expanduser() if args.log_file else None
    translator = build_translator(args.translation_provider, args.translate_to)
    whisper_task = "translate" if args.translate_to and args.translation_provider in ("auto", "whisper") and args.translate_to.lower() in ("en", "english") and not args.bilingual else "transcribe"
    transcriber = FasterWhisperTranscriber(
        model_name=args.model,
        language=args.language,
        device=args.device,
        compute_type=args.compute_type,
        beam_size=args.beam_size,
        task=whisper_task,
    )

    frame = FrameMsg()
    audio = RxAudio(streaming=True)
    queue = None
    pcm_buffer = bytearray()
    bytes_per_second = args.sample_rate * 2
    window_bytes = max(2, int(args.window_duration * bytes_per_second))
    step_seconds = max(0.1, args.window_duration - args.overlap_duration)
    step_bytes = max(2, int(step_seconds * bytes_per_second))
    last_message = ""
    unicode_mode = choose_unicode_mode(args, ())

    await connect_frame_msg(frame, args.name)
    try:
        queue = await audio.attach(frame)
        await upload_runtime(frame)
        await send_status_text(frame, f"{args.prefix} frame mic live ready", args, unicode_mode)

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
                print(f"[frame-mic] rms={rms:.4f}")
                if rms < args.min_rms:
                    continue

                text = await asyncio.to_thread(transcriber.transcribe, samples)
                if not text:
                    continue

                translated = await maybe_translate(text, translator, args.language)
                message = build_display_text(args.prefix, text, translated, args.bilingual)
                if message == last_message:
                    continue

                print(f"[frame-mic] transcript={message}")
                append_log(log_file, message)
                await send_status_text(frame, message, args, unicode_mode)
                last_message = message
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
            print(f"[frame-mic] reconnect attempt {restart_count}: {exc!r}")
            if args.max_restarts and restart_count > args.max_restarts:
                raise
            await asyncio.sleep(args.restart_delay)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nFrame mic live HUD stopped.")


if __name__ == "__main__":
    main()
