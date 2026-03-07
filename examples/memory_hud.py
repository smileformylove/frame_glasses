import argparse
import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from frame_utils import FrameDisplay, FrameUnicodeDisplay, compact_text
from vision_hud import build_analyzer, choose_display, load_or_capture_image


DEFAULT_STORE_PATH = Path("./memory/frame_memory.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Remember scenes and recall notes when you see them again with Frame")
    subparsers = parser.add_subparsers(dest="command", required=True)

    remember = subparsers.add_parser("remember", help="Capture or load an image and store a memory note")
    add_shared_source_args(remember)
    remember.add_argument("--note", default=None, help="Explicit memory note to store. Defaults to analyzer output")
    remember.add_argument("--tag", action="append", default=[], help="Optional tag, can be repeated")
    remember.add_argument("--store", default=str(DEFAULT_STORE_PATH), help="Path to the memory JSON store")
    remember.add_argument("--show-on-frame", action="store_true", help="Display the stored note back on Frame")

    recall = subparsers.add_parser("recall", help="Capture or load an image and recall the nearest memory note")
    add_shared_source_args(recall)
    recall.add_argument("--store", default=str(DEFAULT_STORE_PATH), help="Path to the memory JSON store")
    recall.add_argument("--threshold", type=int, default=12, help="Maximum perceptual hash distance for a memory match")
    recall.add_argument("--show-distance", action="store_true", help="Include hash distance in console output")

    list_cmd = subparsers.add_parser("list", help="List stored memories")
    list_cmd.add_argument("--store", default=str(DEFAULT_STORE_PATH), help="Path to the memory JSON store")

    forget = subparsers.add_parser("forget", help="Delete a stored memory by id")
    forget.add_argument("id", help="Memory id to remove")
    forget.add_argument("--store", default=str(DEFAULT_STORE_PATH), help="Path to the memory JSON store")

    return parser


def add_shared_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", help="Optional BLE device name such as 'Frame 4F'", default=None)
    parser.add_argument("--source", choices=("frame", "image", "demo"), default="frame", help="Where the image comes from")
    parser.add_argument("--image", help="Local image path when --source image is used", default=None)
    parser.add_argument("--output-dir", default="./captures", help="Directory for captured or generated images")
    parser.add_argument("--filename-prefix", default="memory", help="Prefix for saved images")
    parser.add_argument("--analyzer", choices=("mock", "ocr", "openai"), default="mock", help="Image analysis backend")
    parser.add_argument("--mock-result", default="Detected a familiar object.", help="Result text used by the mock analyzer")
    parser.add_argument("--question", default="Describe the most important object or text in one short sentence.", help="Prompt for the vision analyzer")
    parser.add_argument("--output-language", default=None, help="Preferred output language for OpenAI vision")
    parser.add_argument("--ocr-language", default="eng", help="Tesseract language code, for example eng or chi_sim+eng")
    parser.add_argument("--openai-model", default="gpt-4.1-mini", help="OpenAI model for vision analysis")
    parser.add_argument("--dry-run", action="store_true", help="Print locally instead of reconnecting to Frame to display results")
    parser.add_argument("--render-mode", choices=("auto", "plain", "unicode"), default="auto", help="Result rendering mode on Frame")
    parser.add_argument("--font-family", default=None, help="Optional font path for unicode rendering")
    parser.add_argument("--font-size", type=int, default=28, help="Unicode result font size")
    parser.add_argument("--display-width", type=int, default=600, help="Unicode result layout width")
    parser.add_argument("--max-rows", type=int, default=3, help="Maximum unicode result rows")
    parser.add_argument("--x", type=int, default=1, help="Display x coordinate")
    parser.add_argument("--y", type=int, default=1, help="Display y coordinate")
    parser.add_argument("--limit", type=int, default=80, help="Maximum plain-text result length")
    parser.add_argument("--resolution", type=int, default=512, help="Frame capture resolution")
    parser.add_argument("--quality-index", type=int, default=4, help="Frame JPEG quality index")
    parser.add_argument("--pan", type=int, default=0, help="Frame camera pan offset")
    parser.add_argument("--capture-timeout", type=float, default=20.0, help="Seconds to wait for a photo from Frame")
    parser.add_argument("--demo-text", default="Frame Memory Demo\nDesk label", help="Text rendered into the generated demo image")
    parser.add_argument("--keep-image", action="store_true", help="Keep the generated demo image")


def compute_average_hash(image_path: Path) -> str:
    image = Image.open(image_path).convert("L").resize((8, 8), Image.Resampling.LANCZOS)
    pixels = list(image.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if pixel >= avg else "0" for pixel in pixels)
    return f"{int(bits, 2):016x}"


def hamming_distance(hex_a: str, hex_b: str) -> int:
    return bin(int(hex_a, 16) ^ int(hex_b, 16)).count("1")


def load_store(store_path: Path) -> List[Dict[str, Any]]:
    if not store_path.exists():
        return []
    return json.loads(store_path.read_text(encoding="utf-8"))


def save_store(store_path: Path, items: List[Dict[str, Any]]) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


async def analyze_image(args, image_path: Path) -> str:
    analyzer = build_analyzer(args)
    print(f"[memory] analyzer={args.analyzer}")
    print(f"[memory] image={image_path}")
    return await asyncio.to_thread(analyzer.analyze, image_path, args.question)


async def display_result(args, text: str) -> None:
    display = choose_display(args, text)
    rendered = text if isinstance(display, FrameUnicodeDisplay) else compact_text(text, args.limit)
    await display.connect()
    try:
        await display.show_text(rendered, x=args.x, y=args.y)
    finally:
        await display.disconnect()


async def remember(args) -> None:
    store_path = Path(args.store).expanduser()
    image_path = await load_or_capture_image(args)
    analysis = await analyze_image(args, image_path)
    note = args.note or analysis
    item = {
        "id": str(uuid.uuid4())[:8],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "note": note,
        "analysis": analysis,
        "tags": args.tag,
        "image_hash": compute_average_hash(image_path),
        "image_path": str(image_path),
        "source": args.source,
    }
    items = load_store(store_path)
    items.append(item)
    save_store(store_path, items)
    print(f"[memory] saved {item['id']} -> {note}")
    if args.show_on_frame:
        await display_result(args, f"MEMORY saved: {note}")


async def recall(args) -> None:
    store_path = Path(args.store).expanduser()
    items = load_store(store_path)
    if not items:
        message = "MEMORY no saved items yet"
        print(message)
        await display_result(args, message)
        return

    image_path = await load_or_capture_image(args)
    query_hash = compute_average_hash(image_path)
    best_item = None
    best_distance = None

    for item in items:
        distance = hamming_distance(query_hash, item["image_hash"])
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_item = item

    if best_item is None or best_distance is None or best_distance > args.threshold:
        analysis = await analyze_image(args, image_path)
        message = f"MEMORY no match. Saw: {analysis}"
        print(message)
        await display_result(args, message)
        return

    distance_suffix = f" (d={best_distance})" if args.show_distance else ""
    message = f"MEMORY {best_item['note']}{distance_suffix}"
    print(f"[memory] matched {best_item['id']} -> {best_item['note']} distance={best_distance}")
    await display_result(args, message)


def list_memories(args) -> None:
    store_path = Path(args.store).expanduser()
    items = load_store(store_path)
    if not items:
        print("No memories stored yet.")
        return
    for item in items:
        tags = ", ".join(item.get("tags") or [])
        tag_suffix = f" tags=[{tags}]" if tags else ""
        print(f"{item['id']}  {item['created_at']}  {item['note']}{tag_suffix}")


def forget_memory(args) -> None:
    store_path = Path(args.store).expanduser()
    items = load_store(store_path)
    filtered = [item for item in items if item["id"] != args.id]
    if len(filtered) == len(items):
        print(f"Memory id not found: {args.id}")
        return
    save_store(store_path, filtered)
    print(f"Removed memory: {args.id}")


async def async_main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "remember":
        await remember(args)
        return
    if args.command == "recall":
        await recall(args)
        return
    if args.command == "list":
        list_memories(args)
        return
    if args.command == "forget":
        forget_memory(args)
        return

    raise ValueError(f"Unsupported command: {args.command}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
