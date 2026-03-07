import argparse
import asyncio
import re
from argparse import Namespace
from pathlib import Path
from typing import Optional, Tuple

from frame_utils import FrameUnicodeDisplay, compact_text
from meeting_hud import (
    FasterWhisperTranscriber,
    capture_audio_chunk,
    compute_rms,
    list_audio_devices,
    normalize_audio,
    parse_audio_device,
)
from memory_hud import compute_average_hash, hamming_distance, load_store, save_store
from vision_hud import build_analyzer, choose_display, load_or_capture_image


DEFAULT_COMMANDS = "help|describe this|remember this|recall this|exit"
DEFAULT_HELP_TEXT = "VOICE help: describe, read, remember, recall, translate, exit"
DEFAULT_TRANSLATE_LANGUAGE = "English"


class VoiceIntent:
    def __init__(self, action: str, target_language: Optional[str] = None, note: Optional[str] = None, raw: str = ""):
        self.action = action
        self.target_language = target_language
        self.note = note
        self.raw = raw


EXIT_WORDS = ("exit", "quit", "stop", "goodbye", "结束", "退出", "停止")
HELP_WORDS = ("help", "what can you do", "commands", "帮助", "你能做什么")
REMEMBER_WORDS = ("remember", "save this", "记住", "保存这个", "存下来")
RECALL_WORDS = ("recall", "remembered", "do i know this", "回忆", "我见过吗", "之前见过")
READ_WORDS = ("read", "ocr", "read this", "text", "读一下", "读出来", "识别文字")
TRANSLATE_WORDS = ("translate", "翻译")
DESCRIBE_WORDS = ("describe", "what is this", "what am i looking at", "analyze", "这是什么", "我在看什么", "描述一下")


LANGUAGE_ALIASES = {
    "english": "English",
    "英文": "English",
    "英语": "English",
    "en": "English",
    "chinese": "Chinese",
    "中文": "Chinese",
    "汉语": "Chinese",
    "zh": "Chinese",
    "japanese": "Japanese",
    "日文": "Japanese",
    "日语": "Japanese",
    "ja": "Japanese",
    "korean": "Korean",
    "韩文": "Korean",
    "韩语": "Korean",
    "ko": "Korean",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Listen for voice commands, then trigger Frame vision and memory workflows")
    parser.add_argument("--name", help="Optional BLE device name such as 'Frame 4F'", default=None)
    parser.add_argument("--source", choices=("frame", "image", "demo"), default="frame", help="Image source used after a command")
    parser.add_argument("--image", help="Local image path when --source image is used", default=None)
    parser.add_argument("--output-dir", default="./captures", help="Directory for captured or generated images")
    parser.add_argument("--filename-prefix", default="voice", help="Prefix for saved images")
    parser.add_argument("--store", default="./memory/frame_memory.json", help="Path to the memory JSON store")
    parser.add_argument("--threshold", type=int, default=12, help="Maximum perceptual hash distance for memory recall")
    parser.add_argument("--analyzer", choices=("mock", "ocr", "openai"), default="mock", help="Default analyzer for describe and remember")
    parser.add_argument("--mock-result", default="Detected a familiar object.", help="Result text used by the mock analyzer")
    parser.add_argument("--question", default="Describe the most important object or text in one short sentence.", help="Prompt for describe commands")
    parser.add_argument("--output-language", default=None, help="Preferred output language for describe results")
    parser.add_argument("--ocr-language", default="eng", help="Tesseract language code, for example eng or chi_sim+eng")
    parser.add_argument("--openai-model", default="gpt-4.1-mini", help="OpenAI model for vision analysis")
    parser.add_argument("--dry-run", action="store_true", help="Print results locally instead of reconnecting to Frame to display them")
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
    parser.add_argument("--demo-text", default="Frame Voice Demo\nDesk label", help="Text rendered into the generated demo image")
    parser.add_argument("--keep-image", action="store_true", help="Keep generated demo images")
    parser.add_argument("--list-devices", action="store_true", help="List audio input devices and exit")
    parser.add_argument("--audio-device", help="Audio device index or name", default=None)
    parser.add_argument("--listen-duration", type=float, default=3.0, help="Seconds recorded per command attempt")
    parser.add_argument("--samplerate", type=int, default=16000, help="Audio sample rate")
    parser.add_argument("--min-rms", type=float, default=0.015, help="Silence threshold for command audio")
    parser.add_argument("--model", default="base", help="faster-whisper model name")
    parser.add_argument("--language", default=None, help="Optional spoken command language code such as en or zh")
    parser.add_argument("--device", default="auto", help="Whisper device, usually auto or cpu on macOS")
    parser.add_argument("--compute-type", default="int8", help="Whisper compute type")
    parser.add_argument("--beam-size", type=int, default=1, help="Whisper beam size")
    parser.add_argument("--translate-default-language", default=DEFAULT_TRANSLATE_LANGUAGE, help="Default target language when the command says translate without naming one")
    parser.add_argument("--demo", action="store_true", help="Run a local demo without using the microphone")
    parser.add_argument("--demo-commands", default=DEFAULT_COMMANDS, help="Pipe-separated command phrases used in demo mode")
    return parser


def clone_args(args, **overrides):
    values = vars(args).copy()
    values.update(overrides)
    return Namespace(**values)


def parse_target_language(text: str, default_language: str) -> str:
    lowered = text.lower()
    for alias, canonical in LANGUAGE_ALIASES.items():
        if alias in lowered:
            return canonical
    return default_language


def parse_remember_note(text: str) -> Optional[str]:
    patterns = [
        r"remember this as (.+)",
        r"save this as (.+)",
        r"记住这个[:：]?\s*(.+)",
        r"把这个记成[:：]?\s*(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def parse_intent(text: str, default_translate_language: str) -> VoiceIntent:
    lowered = text.lower().strip()
    if not lowered:
        return VoiceIntent("unknown", raw=text)
    if any(word in lowered for word in EXIT_WORDS):
        return VoiceIntent("exit", raw=text)
    if any(word in lowered for word in HELP_WORDS):
        return VoiceIntent("help", raw=text)
    if any(word in lowered for word in REMEMBER_WORDS):
        return VoiceIntent("remember", note=parse_remember_note(text), raw=text)
    if any(word in lowered for word in RECALL_WORDS):
        return VoiceIntent("recall", raw=text)
    if any(word in lowered for word in TRANSLATE_WORDS):
        return VoiceIntent("translate", target_language=parse_target_language(text, default_translate_language), raw=text)
    if any(word in lowered for word in READ_WORDS):
        return VoiceIntent("read", raw=text)
    if any(word in lowered for word in DESCRIBE_WORDS):
        return VoiceIntent("describe", raw=text)
    return VoiceIntent("unknown", raw=text)


async def analyze_image(args, image_path: Path, analyzer_name: str, prompt: str, output_language: Optional[str] = None) -> str:
    analyzer_args = clone_args(args, analyzer=analyzer_name, output_language=output_language)
    analyzer = build_analyzer(analyzer_args)
    return await asyncio.to_thread(analyzer.analyze, image_path, prompt)


async def display_text(args, text: str) -> None:
    display = choose_display(args, text)
    rendered = text if isinstance(display, FrameUnicodeDisplay) else compact_text(text, args.limit)
    await display.connect()
    try:
        await display.show_text(rendered, x=args.x, y=args.y)
    finally:
        await display.disconnect()


async def load_command_image(args) -> Path:
    return await load_or_capture_image(args)


def ensure_store(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        save_store(path, [])


async def remember_scene(args, image_path: Path, note: Optional[str]) -> str:
    store_path = Path(args.store).expanduser()
    ensure_store(store_path)
    items = load_store(store_path)
    analysis = await analyze_image(args, image_path, args.analyzer, args.question, args.output_language)
    final_note = note or analysis
    item = {
        "id": str(len(items) + 1).zfill(4),
        "created_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "note": final_note,
        "analysis": analysis,
        "tags": ["voice-memory"],
        "image_hash": compute_average_hash(image_path),
        "image_path": str(image_path),
        "source": "voice-command",
    }
    items.append(item)
    save_store(store_path, items)
    return f"MEMORY saved: {final_note}"


async def recall_scene(args, image_path: Path) -> str:
    store_path = Path(args.store).expanduser()
    ensure_store(store_path)
    items = load_store(store_path)
    if not items:
        return "MEMORY empty. Say remember this first."

    query_hash = compute_average_hash(image_path)
    best_item = None
    best_distance = None
    for item in items:
        distance = hamming_distance(query_hash, item["image_hash"])
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_item = item

    if best_item is None or best_distance is None or best_distance > args.threshold:
        analysis = await analyze_image(args, image_path, args.analyzer, args.question, args.output_language)
        return f"MEMORY no match. Saw: {analysis}"
    return f"MEMORY {best_item['note']}"


async def execute_intent(args, intent: VoiceIntent) -> Tuple[str, bool]:
    if intent.action == "help":
        return DEFAULT_HELP_TEXT, False
    if intent.action == "exit":
        return "VOICE stopping", True
    if intent.action == "unknown":
        return "VOICE unknown command. Say help.", False

    image_path = await load_command_image(args)
    try:
        if intent.action == "describe":
            result = await analyze_image(args, image_path, args.analyzer, args.question, args.output_language)
            return f"VISION {result}", False
        if intent.action == "read":
            result = await analyze_image(args, image_path, "ocr", "Read visible text exactly.", args.output_language)
            return f"READ {result}", False
        if intent.action == "translate":
            target = intent.target_language or args.translate_default_language
            prompt = f"Read the important visible text and translate it to {target} in one concise sentence for smart glasses."
            result = await analyze_image(args, image_path, "openai", prompt, target)
            return f"TRANS {result}", False
        if intent.action == "remember":
            return await remember_scene(args, image_path, intent.note), False
        if intent.action == "recall":
            return await recall_scene(args, image_path), False
        return "VOICE unsupported command.", False
    finally:
        if args.source == "demo" and not args.keep_image:
            image_path.unlink(missing_ok=True)


async def run_demo(args) -> None:
    commands = [part.strip() for part in args.demo_commands.split("|") if part.strip()]
    for command_text in commands:
        print(f"[voice] heard={command_text}")
        intent = parse_intent(command_text, args.translate_default_language)
        try:
            message, should_exit = await execute_intent(args, intent)
        except Exception as exc:
            message, should_exit = f"VOICE error: {exc}", False
        print(f"[voice] result={message}")
        if not args.dry_run:
            await display_text(args, message)
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

    await display_text(args, "VOICE ready. Say help, describe, read, remember, recall, translate, or exit.")

    while True:
        audio_chunk = await asyncio.to_thread(capture_audio_chunk, args.listen_duration, args.samplerate, parse_audio_device(args.audio_device))
        rms = compute_rms(audio_chunk)
        print(f"[voice] rms={rms:.4f}")
        if rms < args.min_rms:
            continue

        normalized = normalize_audio(audio_chunk)
        text = await asyncio.to_thread(transcriber.transcribe, normalized)
        if not text:
            continue

        print(f"[voice] heard={text}")
        intent = parse_intent(text, args.translate_default_language)
        try:
            message, should_exit = await execute_intent(args, intent)
        except Exception as exc:
            message, should_exit = f"VOICE error: {exc}", False
        print(f"[voice] result={message}")
        await display_text(args, message)
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
        print("\nVoice Command HUD stopped.")


if __name__ == "__main__":
    main()
