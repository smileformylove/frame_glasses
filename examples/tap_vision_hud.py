import argparse
import asyncio
from pathlib import Path
from typing import Optional

from frame_msg import FrameMsg, RxPhoto, RxTap, TxCaptureSettings

from frame_utils import build_unicode_payloads, compact_text, resolve_unicode_font
from vision_hud import (
    CAPTURE_MSG_CODE,
    DEFAULT_VISION_PROMPT,
    build_analyzer,
    connect_frame_msg,
    create_demo_image,
    timestamped_image_path,
)

PLAIN_TEXT_MSG_CODE = 0x21
UNICODE_TEXT_MSG_CODE = 0x20


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wait for a tap on Frame, capture a photo, analyze it, and send the result back to the glasses")
    parser.add_argument("--name", help="Optional BLE device name such as 'Frame 4F'", default=None)
    parser.add_argument("--analyzer", choices=("mock", "ocr", "openai"), default="mock", help="Image analysis backend")
    parser.add_argument("--mock-result", default="Detected a sticky note on the desk.", help="Result text used by the mock analyzer")
    parser.add_argument("--question", default=DEFAULT_VISION_PROMPT, help="Prompt for the vision analyzer")
    parser.add_argument("--output-language", default=None, help="Preferred output language for OpenAI vision")
    parser.add_argument("--ocr-language", default="eng", help="Tesseract language code, for example eng or chi_sim+eng")
    parser.add_argument("--openai-model", default="gpt-4.1-mini", help="OpenAI model for vision analysis")
    parser.add_argument("--render-mode", choices=("auto", "plain", "unicode"), default="auto", help="How results are rendered back on Frame")
    parser.add_argument("--font-family", default=None, help="Optional font path for unicode rendering")
    parser.add_argument("--font-size", type=int, default=28, help="Unicode result font size")
    parser.add_argument("--display-width", type=int, default=600, help="Unicode result layout width")
    parser.add_argument("--max-rows", type=int, default=3, help="Maximum unicode result rows")
    parser.add_argument("--limit", type=int, default=80, help="Maximum ASCII message length for plain mode")
    parser.add_argument("--resolution", type=int, default=512, help="Frame capture resolution, even number between 100 and 720")
    parser.add_argument("--quality-index", type=int, default=4, help="Frame JPEG quality index between 0 and 4")
    parser.add_argument("--pan", type=int, default=0, help="Frame camera pan offset")
    parser.add_argument("--capture-timeout", type=float, default=20.0, help="Seconds to wait for a photo after a tap")
    parser.add_argument("--output-dir", default="./captures", help="Directory for captured images")
    parser.add_argument("--filename-prefix", default="tap_vision", help="Prefix for saved captures")
    parser.add_argument("--tap-threshold", type=float, default=0.3, help="Tap grouping threshold in seconds")
    parser.add_argument("--single-tap-captures", action="store_true", default=True, help="Single tap triggers capture")
    parser.add_argument("--double-tap-exits", action="store_true", default=True, help="Double tap exits the loop")
    parser.add_argument("--dry-run", action="store_true", help="Print final result locally instead of sending it back to Frame")
    parser.add_argument("--demo", action="store_true", help="Run a local tap demo without connecting to Frame")
    parser.add_argument("--demo-taps", default="1,2", help="Comma-separated simulated tap counts for demo mode, for example 1,1,2")
    parser.add_argument("--demo-text", default="Frame Tap Vision Demo\nTap once to capture", help="Text rendered into the generated demo image")
    parser.add_argument("--keep-image", action="store_true", help="Keep generated demo images")
    return parser


async def upload_tap_vision_runtime(frame: FrameMsg) -> str:
    frame_app_name = "tap_vision_frame_app"
    frame_app_path = Path(__file__).resolve().parent / "frame_apps" / f"{frame_app_name}.lua"
    await frame.upload_stdlua_libs(["data", "camera", "tap", "text_sprite_block"])
    await frame.upload_frame_app(str(frame_app_path), f"{frame_app_name}.lua")
    await frame.start_frame_app(frame_app_name, await_print=True)
    return frame_app_name


def parse_demo_taps(raw: str) -> list[int]:
    values = []
    for part in raw.split(','):
        stripped = part.strip()
        if not stripped:
            continue
        values.append(int(stripped))
    return values or [1, 2]


def should_use_unicode(render_mode: str, text: str) -> bool:
    if render_mode == "unicode":
        return True
    if render_mode == "plain":
        return False
    return any(ord(char) > 127 for char in text) or "\n" in text


async def send_status_text(frame: FrameMsg, text: str, args) -> None:
    if should_use_unicode(args.render_mode, text):
        payloads = build_unicode_payloads(
            text=text,
            font_family=resolve_unicode_font(args.font_family),
            font_size=args.font_size,
            display_width=args.display_width,
            max_rows=args.max_rows,
            x=1,
            y=1,
        )
        for payload in payloads:
            await frame.send_message(UNICODE_TEXT_MSG_CODE, payload)
        return

    await frame.send_message(PLAIN_TEXT_MSG_CODE, compact_text(text, args.limit).encode("utf-8"))


async def capture_photo(frame: FrameMsg, photo_queue: asyncio.Queue, args, image_path: Path) -> Path:
    await frame.send_message(PLAIN_TEXT_MSG_CODE, b"capturing...")
    capture_settings = TxCaptureSettings(
        resolution=args.resolution,
        quality_index=args.quality_index,
        pan=args.pan,
    )
    await frame.send_message(CAPTURE_MSG_CODE, capture_settings.pack())
    image_bytes = await asyncio.wait_for(photo_queue.get(), timeout=args.capture_timeout)
    image_path.write_bytes(image_bytes)
    return image_path


async def analyze_and_report(image_path: Path, args) -> str:
    analyzer = build_analyzer(args)
    print(f"[vision] analyzer={args.analyzer}")
    print(f"[vision] image={image_path}")
    result = await asyncio.to_thread(analyzer.analyze, image_path, args.question)
    print(f"[vision] result={result}")
    return result


async def run_demo(args) -> None:
    demo_taps = parse_demo_taps(args.demo_taps)
    output_dir = Path(args.output_dir).expanduser()
    image_path = timestamped_image_path(output_dir, f"{args.filename_prefix}_demo")
    create_demo_image(image_path, args.demo_text)
    try:
        for tap_count in demo_taps:
            print(f"[tap] count={tap_count}")
            if tap_count >= 2 and args.double_tap_exits:
                print("[tap] double tap received, demo exits")
                break
            if tap_count >= 1 and args.single_tap_captures:
                result = await analyze_and_report(image_path, args)
                print(f"[tap-vision dry-run] {result}")
        return
    finally:
        if not args.keep_image:
            image_path.unlink(missing_ok=True)


async def run_live(args) -> None:
    frame = FrameMsg()
    tap = RxTap(threshold=args.tap_threshold)
    photo = RxPhoto(upright=True)
    output_dir = Path(args.output_dir).expanduser()
    tap_queue = None
    photo_queue = None

    await connect_frame_msg(frame, args.name)
    try:
        tap_queue = await tap.attach(frame)
        photo_queue = await photo.attach(frame)
        await upload_tap_vision_runtime(frame)
        await send_status_text(frame, "Tap side to capture. Double tap exits.", args)

        while True:
            tap_count = await tap_queue.get()
            print(f"[tap] count={tap_count}")

            if tap_count >= 2 and args.double_tap_exits:
                await send_status_text(frame, "Tap Vision HUD stopped.", args)
                break

            if tap_count < 1 or not args.single_tap_captures:
                continue

            image_path = timestamped_image_path(output_dir, args.filename_prefix)
            await send_status_text(frame, "Capturing and analyzing...", args)
            await capture_photo(frame, photo_queue, args, image_path)
            result = await analyze_and_report(image_path, args)

            if args.dry_run:
                print(f"[tap-vision dry-run] {result}")
            else:
                await send_status_text(frame, f"VISION {result}", args)
    finally:
        if photo_queue is not None:
            photo.detach(frame)
        if tap_queue is not None:
            tap.detach(frame)
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
        print("\nTap Vision HUD stopped.")


if __name__ == "__main__":
    main()
