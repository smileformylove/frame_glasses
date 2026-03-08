import argparse
import asyncio
import base64
import io
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from frame_msg import FrameMsg, RxPhoto, TxCaptureSettings

from frame_utils import FrameDisplay, FrameUnicodeDisplay, compact_text, sleep_briefly, connect_with_retry, initialize_frame


CAPTURE_MSG_CODE = 0x0D
DEFAULT_VISION_PROMPT = "Read any visible text and summarize what is important in one short sentence for smart glasses."


class MockVisionAnalyzer:
    def __init__(self, result: str) -> None:
        self.result = result

    def analyze(self, image_path: Path, prompt: str) -> str:
        _ = image_path, prompt
        return self.result


class TesseractVisionAnalyzer:
    def __init__(self, language: str) -> None:
        import pytesseract

        self.language = language
        self._pytesseract = pytesseract

    def analyze(self, image_path: Path, prompt: str) -> str:
        from PIL import Image

        _ = prompt
        text = self._pytesseract.image_to_string(Image.open(image_path), lang=self.language)
        cleaned = " ".join(text.split())
        if not cleaned:
            return "No clear text detected."
        return compact_text(cleaned, 140)


class OpenAIVisionAnalyzer:
    def __init__(self, model: str, output_language: Optional[str]) -> None:
        from openai import OpenAI
        import os

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI vision mode")

        self.model = model
        self.output_language = output_language
        self.client = OpenAI(api_key=api_key)

    def analyze(self, image_path: Path, prompt: str) -> str:
        data_url = path_to_data_url(image_path)
        language_hint = self.output_language or "same as the important text in the image"
        response = self.client.responses.create(
            model=self.model,
            instructions=(
                "You are helping smart glasses users. Return only one concise sentence. "
                "Prefer the language requested by the user. If visible text is important, read it accurately."
            ),
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": f"{prompt}\nAnswer language: {language_hint}"},
                        {"type": "input_image", "image_url": data_url, "detail": "auto"},
                    ],
                }
            ],
            temperature=0.2,
            max_output_tokens=120,
        )
        output_text = getattr(response, "output_text", "")
        if output_text:
            return " ".join(output_text.split())
        raise RuntimeError("OpenAI vision response returned no text")


async def connect_frame_msg(frame: FrameMsg, name: Optional[str], verbose: bool = False) -> None:
    await connect_with_retry(frame.ble, name=name, verbose=verbose, data_response_handler=frame._handle_data_response)
    await initialize_frame(frame.ble, verbose=verbose)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture from Frame or load a local image, then analyze it and send a short result back to Frame")
    parser.add_argument("--name", help="Optional BLE device name such as 'Frame 4F'", default=None)
    parser.add_argument("--source", choices=("frame", "image", "demo"), default="frame", help="Where the image comes from")
    parser.add_argument("--image", help="Local image path when --source image is used", default=None)
    parser.add_argument("--output-dir", default="./captures", help="Directory for captured or generated images")
    parser.add_argument("--filename-prefix", default="vision", help="Prefix for saved images")
    parser.add_argument("--analyzer", choices=("mock", "ocr", "openai"), default="mock", help="Image analysis backend")
    parser.add_argument("--mock-result", default="Detected a demo label on the desk.", help="Result text used by the mock analyzer")
    parser.add_argument("--question", default=DEFAULT_VISION_PROMPT, help="Prompt for the vision analyzer")
    parser.add_argument("--output-language", default=None, help="Preferred output language for OpenAI vision")
    parser.add_argument("--ocr-language", default="eng", help="Tesseract language code, for example eng or chi_sim+eng")
    parser.add_argument("--openai-model", default="gpt-4.1-mini", help="OpenAI model for vision analysis")
    parser.add_argument("--dry-run", action="store_true", help="Print the final result locally instead of reconnecting to Frame to display it")
    parser.add_argument("--render-mode", choices=("auto", "plain", "unicode"), default="auto", help="Result rendering mode on Frame")
    parser.add_argument("--font-family", default=None, help="Optional font path for unicode rendering")
    parser.add_argument("--font-size", type=int, default=28, help="Unicode result font size")
    parser.add_argument("--display-width", type=int, default=600, help="Unicode result layout width")
    parser.add_argument("--max-rows", type=int, default=3, help="Maximum unicode result rows")
    parser.add_argument("--x", type=int, default=1, help="Display x coordinate")
    parser.add_argument("--y", type=int, default=1, help="Display y coordinate")
    parser.add_argument("--limit", type=int, default=80, help="Maximum plain-text result length")
    parser.add_argument("--resolution", type=int, default=512, help="Frame capture resolution, even number between 100 and 720")
    parser.add_argument("--quality-index", type=int, default=4, help="Frame JPEG quality index between 0 and 4")
    parser.add_argument("--pan", type=int, default=0, help="Frame camera pan offset")
    parser.add_argument("--capture-timeout", type=float, default=20.0, help="Seconds to wait for a photo from Frame")
    parser.add_argument("--demo-text", default="Frame OCR demo\nOpenAI Vision HUD", help="Text rendered into the generated demo image")
    parser.add_argument("--keep-image", action="store_true", help="Keep the generated demo image instead of deleting it later")
    return parser


def build_analyzer(args):
    if args.analyzer == "mock":
        return MockVisionAnalyzer(args.mock_result)
    if args.analyzer == "ocr":
        return TesseractVisionAnalyzer(args.ocr_language)
    if args.analyzer == "openai":
        return OpenAIVisionAnalyzer(args.openai_model, args.output_language)
    raise ValueError(f"Unsupported analyzer: {args.analyzer}")


def choose_display(args, result_text: str):
    prefers_unicode = args.render_mode == "unicode" or (
        args.render_mode == "auto" and any(ord(char) > 127 for char in result_text)
    )
    if prefers_unicode:
        return FrameUnicodeDisplay(
            name=args.name,
            dry_run=args.dry_run,
            font_family=args.font_family,
            font_size=args.font_size,
            display_width=args.display_width,
            max_rows=args.max_rows,
        )
    return FrameDisplay(name=args.name, dry_run=args.dry_run)


def path_to_data_url(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(image_path))
    mime_type = mime_type or "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def timestamped_image_path(output_dir: Path, prefix: str, suffix: str = ".jpg") -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{prefix}_{stamp}{suffix}"


def create_demo_image(output_path: Path, text: str) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (900, 520), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 36)
    except OSError:
        font = ImageFont.load_default()

    draw.rounded_rectangle((50, 50, 850, 470), radius=24, outline="black", width=4, fill="#f7f7f7")
    draw.text((90, 110), text, fill="black", font=font, spacing=14)
    draw.text((90, 360), "Vision HUD demo image", fill="#444444", font=font)
    image.save(output_path, format="JPEG")
    return output_path


async def capture_from_frame(args, output_path: Path) -> Path:
    frame = FrameMsg()
    photo = RxPhoto(upright=True)
    queue = None
    frame_app_name = "vision_camera_frame_app"
    frame_app_path = Path(__file__).resolve().parent / "frame_apps" / f"{frame_app_name}.lua"

    await connect_frame_msg(frame, args.name)
    try:
        queue = await photo.attach(frame)
        await frame.upload_stdlua_libs(["data", "camera"])
        await frame.upload_frame_app(str(frame_app_path), f"{frame_app_name}.lua")
        await frame.start_frame_app(frame_app_name, await_print=True)
        capture_settings = TxCaptureSettings(
            resolution=args.resolution,
            quality_index=args.quality_index,
            pan=args.pan,
        )
        await frame.send_message(CAPTURE_MSG_CODE, capture_settings.pack())
        image_bytes = await asyncio.wait_for(queue.get(), timeout=args.capture_timeout)
        output_path.write_bytes(image_bytes)
        return output_path
    finally:
        if queue is not None:
            photo.detach(frame)
        try:
            await frame.stop_frame_app(reset=True)
        except Exception:
            pass
        if frame.is_connected():
            await frame.disconnect()


async def load_or_capture_image(args) -> Path:
    output_dir = Path(args.output_dir).expanduser()
    if args.source == "image":
        if not args.image:
            raise ValueError("--image is required when --source image is used")
        image_path = Path(args.image).expanduser()
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        return image_path

    if args.source == "demo":
        output_path = timestamped_image_path(output_dir, f"{args.filename_prefix}_demo")
        return create_demo_image(output_path, args.demo_text)

    output_path = timestamped_image_path(output_dir, args.filename_prefix)
    return await capture_from_frame(args, output_path)


async def analyze_image(args, image_path: Path) -> str:
    analyzer = build_analyzer(args)
    print(f"[vision] analyzer={args.analyzer}")
    print(f"[vision] image={image_path}")
    return await asyncio.to_thread(analyzer.analyze, image_path, args.question)


async def show_result(args, result: str) -> None:
    display_text = f"VISION {result}".strip()
    display = choose_display(args, display_text)
    rendered = display_text if isinstance(display, FrameUnicodeDisplay) else compact_text(display_text, args.limit)
    await sleep_briefly(0.2)
    await display.connect()
    try:
        await display.show_text(rendered, x=args.x, y=args.y)
    finally:
        await display.disconnect()


async def async_main() -> None:
    args = build_parser().parse_args()
    image_path = await load_or_capture_image(args)
    try:
        result = await analyze_image(args, image_path)
        print(f"[vision] result={result}")
        await show_result(args, result)
    finally:
        if args.source == "demo" and not args.keep_image:
            image_path.unlink(missing_ok=True)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nVision HUD stopped.")


if __name__ == "__main__":
    main()
