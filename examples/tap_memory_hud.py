import argparse
import asyncio
from pathlib import Path
from typing import Optional

from frame_msg import FrameMsg, RxPhoto, RxTap

from memory_hud import compute_average_hash, hamming_distance, load_store, save_store
from tap_vision_hud import capture_photo, parse_demo_taps, send_status_text, upload_tap_vision_runtime
from vision_hud import build_analyzer, create_demo_image, timestamped_image_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tap the glasses to recall or save scene memories")
    parser.add_argument("--name", help="Optional BLE device name such as 'Frame 4F'", default=None)
    parser.add_argument("--store", default="./memory/frame_memory.json", help="Path to the memory JSON store")
    parser.add_argument("--threshold", type=int, default=12, help="Maximum perceptual hash distance for a memory match")
    parser.add_argument("--analyzer", choices=("mock", "ocr", "openai"), default="mock", help="Image analysis backend")
    parser.add_argument("--mock-result", default="Detected a familiar desk setup.", help="Result text used by the mock analyzer")
    parser.add_argument("--question", default="Describe the most important object or text in one short sentence.", help="Prompt for the vision analyzer")
    parser.add_argument("--output-language", default=None, help="Preferred output language for OpenAI vision")
    parser.add_argument("--ocr-language", default="eng", help="Tesseract language code, for example eng or chi_sim+eng")
    parser.add_argument("--openai-model", default="gpt-4.1-mini", help="OpenAI model for vision analysis")
    parser.add_argument("--render-mode", choices=("auto", "plain", "unicode"), default="auto", help="How text is rendered back on Frame")
    parser.add_argument("--font-family", default=None, help="Optional font path for unicode rendering")
    parser.add_argument("--font-size", type=int, default=28, help="Unicode result font size")
    parser.add_argument("--display-width", type=int, default=600, help="Unicode result layout width")
    parser.add_argument("--max-rows", type=int, default=3, help="Maximum unicode result rows")
    parser.add_argument("--limit", type=int, default=80, help="Maximum ASCII message length for plain mode")
    parser.add_argument("--resolution", type=int, default=512, help="Frame capture resolution")
    parser.add_argument("--quality-index", type=int, default=4, help="Frame JPEG quality index")
    parser.add_argument("--pan", type=int, default=0, help="Frame camera pan offset")
    parser.add_argument("--capture-timeout", type=float, default=20.0, help="Seconds to wait for a photo from Frame")
    parser.add_argument("--output-dir", default="./captures", help="Directory for captured images")
    parser.add_argument("--filename-prefix", default="tap_memory", help="Prefix for saved captures")
    parser.add_argument("--tap-threshold", type=float, default=0.3, help="Tap grouping threshold in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Print results locally instead of sending them back to Frame")
    parser.add_argument("--demo", action="store_true", help="Run a local tap demo without connecting to Frame")
    parser.add_argument("--demo-taps", default="3,1,2", help="Comma-separated simulated tap counts, for example 3,1,2")
    parser.add_argument("--demo-text", default="Frame Memory Demo\nDesk label", help="Text rendered into the generated demo image")
    parser.add_argument("--keep-image", action="store_true", help="Keep generated demo images")
    return parser


def ensure_store(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        save_store(path, [])


async def analyze_image(args, image_path: Path) -> str:
    analyzer = build_analyzer(args)
    print(f"[memory] analyzer={args.analyzer}")
    print(f"[memory] image={image_path}")
    return await asyncio.to_thread(analyzer.analyze, image_path, args.question)


async def remember_image(args, image_path: Path) -> str:
    store_path = Path(args.store).expanduser()
    ensure_store(store_path)
    items = load_store(store_path)
    analysis = await analyze_image(args, image_path)
    item = {
        "id": str(len(items) + 1).zfill(4),
        "created_at": __import__('datetime').datetime.now().isoformat(timespec="seconds"),
        "note": analysis,
        "analysis": analysis,
        "tags": ["tap-memory"],
        "image_hash": compute_average_hash(image_path),
        "image_path": str(image_path),
        "source": "tap-memory",
    }
    items.append(item)
    save_store(store_path, items)
    print(f"[memory] saved {item['id']} -> {item['note']}")
    return f"MEMORY saved: {item['note']}"


async def recall_image(args, image_path: Path) -> str:
    store_path = Path(args.store).expanduser()
    ensure_store(store_path)
    items = load_store(store_path)
    if not items:
        return "MEMORY empty. Triple tap to save this scene."

    query_hash = compute_average_hash(image_path)
    best_item = None
    best_distance = None
    for item in items:
        distance = hamming_distance(query_hash, item['image_hash'])
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_item = item

    if best_item is None or best_distance is None or best_distance > args.threshold:
        analysis = await analyze_image(args, image_path)
        return f"MEMORY no match. Saw: {analysis}"

    print(f"[memory] matched {best_item['id']} -> {best_item['note']} distance={best_distance}")
    return f"MEMORY {best_item['note']}"


async def run_demo(args) -> None:
    taps = parse_demo_taps(args.demo_taps)
    output_dir = Path(args.output_dir).expanduser()
    store_path = Path(args.store).expanduser()
    ensure_store(store_path)
    image_path = timestamped_image_path(output_dir, f"{args.filename_prefix}_demo")
    create_demo_image(image_path, args.demo_text)
    try:
        for tap_count in taps:
            print(f"[tap] count={tap_count}")
            if tap_count >= 3:
                print(await remember_image(args, image_path))
                continue
            if tap_count >= 2:
                print("[tap-memory] double tap received, demo exits")
                break
            if tap_count >= 1:
                print(await recall_image(args, image_path))
    finally:
        if not args.keep_image:
            image_path.unlink(missing_ok=True)


async def run_live(args) -> None:
    from vision_hud import connect_frame_msg

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
        await asyncio.sleep(args.stabilize_delay)
        await send_status_text(frame, "1 tap recall / 3 taps save / 2 taps exit", args)

        while True:
            tap_count = await tap_queue.get()
            print(f"[tap] count={tap_count}")

            if tap_count >= 2 and tap_count < 3:
                await send_status_text(frame, "Tap Memory HUD stopped.", args)
                break

            image_path = timestamped_image_path(output_dir, args.filename_prefix)
            await send_status_text(frame, "Capturing...", args)
            await capture_photo(frame, photo_queue, args, image_path)

            if tap_count >= 3:
                message = await remember_image(args, image_path)
            else:
                message = await recall_image(args, image_path)

            if args.dry_run:
                print(f"[tap-memory dry-run] {message}")
            else:
                await send_status_text(frame, message, args)
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
        print("\nTap Memory HUD stopped.")


if __name__ == "__main__":
    main()
