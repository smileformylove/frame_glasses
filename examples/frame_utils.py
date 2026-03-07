import asyncio
import re
import unicodedata
from importlib.resources import files
from pathlib import Path
from typing import List, Optional

from frame_ble import FrameBle


DEFAULT_MAC_UNICODE_FONTS = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]
UNICODE_TEXT_MSG_CODE = 0x20


class FrameDisplay:
    def __init__(self, name: Optional[str] = None, dry_run: bool = False):
        self.name = name
        self.dry_run = dry_run
        self.frame: Optional[FrameBle] = None

    async def connect(self) -> None:
        if self.dry_run:
            return

        self.frame = FrameBle()
        await self.frame.connect(name=self.name)
        await self.frame.send_break_signal()
        await self.frame.send_reset_signal()
        await self.frame.send_break_signal()

    async def disconnect(self) -> None:
        if self.dry_run or self.frame is None:
            return

        if self.frame.is_connected():
            await self.frame.disconnect()

    async def show_text(self, text: str, x: int = 1, y: int = 1) -> None:
        if self.dry_run:
            print(f"[Frame dry-run] ({x},{y}) {text}")
            return

        if self.frame is None:
            raise RuntimeError("Frame is not connected")

        command = f"frame.display.text('{lua_escape(text)}',{x},{y});frame.display.show();print(0)"
        await self.frame.send_lua(command, await_print=True)


class FrameUnicodeDisplay:
    def __init__(
        self,
        name: Optional[str] = None,
        dry_run: bool = False,
        font_family: Optional[str] = None,
        font_size: int = 28,
        display_width: int = 600,
        max_rows: int = 2,
    ):
        self.name = name
        self.dry_run = dry_run
        self.font_family = resolve_unicode_font(font_family)
        self.font_size = font_size
        self.display_width = display_width
        self.max_rows = max_rows
        self.frame: Optional[FrameBle] = None

    async def connect(self) -> None:
        if self.dry_run:
            return

        if self.font_family is None:
            raise RuntimeError(
                "No usable Unicode font found. Pass --font-family with a macOS font path, for example /System/Library/Fonts/Hiragino Sans GB.ttc"
            )

        self.frame = FrameBle()
        await self.frame.connect(name=self.name)
        await self.frame.send_break_signal()
        await self.frame.send_reset_signal()
        await self.frame.send_break_signal()
        await self._upload_unicode_runtime()
        await self.frame.send_lua("require('text_sprite_block_frame_app')", await_print=True)

    async def disconnect(self) -> None:
        if self.dry_run or self.frame is None:
            return

        if self.frame.is_connected():
            try:
                await self.frame.send_break_signal()
            except Exception:
                pass
            await self.frame.disconnect()

    async def show_text(self, text: str, x: int = 1, y: int = 1) -> None:
        rendered = wrap_subtitle_text(text, width=self.display_width, font_size=self.font_size, max_lines=self.max_rows)

        if self.dry_run:
            print(f"[Frame unicode dry-run] ({x},{y}) {rendered}")
            return

        if self.frame is None:
            raise RuntimeError("Frame is not connected")

        payloads = build_unicode_payloads(
            text=rendered,
            font_family=self.font_family,
            font_size=self.font_size,
            display_width=self.display_width,
            max_rows=self.max_rows,
            x=x,
            y=y,
        )
        for payload in payloads:
            await self.frame.send_message(UNICODE_TEXT_MSG_CODE, payload)

    async def _upload_unicode_runtime(self) -> None:
        if self.frame is None:
            raise RuntimeError("Frame is not connected")

        lua_dir = Path(files("frame_msg").joinpath("lua"))
        await self.frame.upload_file_from_string(lua_dir.joinpath("data.min.lua").read_text(), "data.min.lua")
        await self.frame.upload_file_from_string(
            lua_dir.joinpath("text_sprite_block.min.lua").read_text(),
            "text_sprite_block.min.lua",
        )

        frame_app = Path(__file__).resolve().parent / "frame_apps" / "text_sprite_block_frame_app.lua"
        await self.frame.upload_file(str(frame_app), frame_app.name)


async def sleep_briefly(seconds: float = 0.05) -> None:
    await asyncio.sleep(seconds)


def lua_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")


def compact_text(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)] + "…"


def resolve_unicode_font(font_family: Optional[str] = None) -> Optional[str]:
    if font_family:
        expanded = Path(font_family).expanduser()
        if expanded.exists():
            return str(expanded)
        return font_family

    for candidate in DEFAULT_MAC_UNICODE_FONTS:
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None


def _char_display_units(char: str) -> float:
    if char == "\n":
        return 0.0
    if char.isspace():
        return 0.5
    width_class = unicodedata.east_asian_width(char)
    if width_class in ("W", "F"):
        return 2.0
    if width_class == "A":
        return 1.5
    return 1.0


def _token_units(token: str) -> float:
    return sum(_char_display_units(char) for char in token)


def _split_long_token(token: str, max_units: int) -> List[str]:
    parts: List[str] = []
    current = ""
    current_units = 0.0

    for char in token:
        char_units = _char_display_units(char)
        if current and current_units + char_units > max_units:
            parts.append(current)
            current = char
            current_units = char_units
        else:
            current += char
            current_units += char_units

    if current:
        parts.append(current)
    return parts


def wrap_subtitle_text(text: str, width: int, font_size: int, max_lines: int) -> str:
    normalized = re.sub(r"[ \t]+", " ", text.replace("\r", "")).strip()
    if not normalized:
        return "…"

    max_units = max(10, int(width / max(font_size * 0.6, 1)))
    lines: List[str] = []

    for paragraph in normalized.split("\n"):
        tokens = re.split(r"(\s+)", paragraph.strip())
        current = ""
        current_units = 0.0

        for token in tokens:
            if not token:
                continue

            if token.isspace():
                if current and not current.endswith(" "):
                    current += " "
                    current_units += _token_units(" ")
                continue

            token_units = _token_units(token)
            if not current:
                if token_units <= max_units:
                    current = token
                    current_units = token_units
                else:
                    parts = _split_long_token(token, max_units)
                    lines.extend(parts[:-1])
                    current = parts[-1]
                    current_units = _token_units(current)
                continue

            separator = "" if current.endswith(" ") else " "
            candidate = current + separator + token
            candidate_units = _token_units(candidate)
            if candidate_units <= max_units:
                current = candidate
                current_units = candidate_units
                continue

            lines.append(current.strip())
            if len(lines) >= max_lines:
                return "\n".join(lines[:max_lines])

            if token_units <= max_units:
                current = token
                current_units = token_units
            else:
                parts = _split_long_token(token, max_units)
                lines.extend(parts[:-1])
                if len(lines) >= max_lines:
                    return "\n".join(lines[:max_lines])
                current = parts[-1]
                current_units = _token_units(current)

        if current.strip():
            lines.append(current.strip())
            if len(lines) >= max_lines:
                return "\n".join(lines[:max_lines])

    if not lines:
        return "…"
    return "\n".join(lines[:max_lines])


def build_unicode_payloads(
    text: str,
    font_family: Optional[str],
    font_size: int,
    display_width: int,
    max_rows: int,
    x: int,
    y: int,
):
    from frame_msg import TxTextSpriteBlock

    block = TxTextSpriteBlock(
        width=display_width,
        font_size=font_size,
        max_display_rows=max_rows,
        text=text,
        font_family=font_family,
    )
    payloads = [offset_text_block(block.pack(), x=x, y=y)]
    payloads.extend(sprite.pack() for sprite in block.sprites)
    return payloads


def offset_text_block(payload: bytes, x: int, y: int) -> bytes:
    shifted = bytearray(payload)
    line_count = shifted[4]
    x_offset = max(0, x - 1)
    y_offset = max(0, y - 1)

    for index in range(line_count):
        pos = 5 + index * 4
        original_y = (shifted[pos + 2] << 8) | shifted[pos + 3]
        adjusted_y = min(65535, y_offset + original_y)
        shifted[pos] = (x_offset >> 8) & 0xFF
        shifted[pos + 1] = x_offset & 0xFF
        shifted[pos + 2] = (adjusted_y >> 8) & 0xFF
        shifted[pos + 3] = adjusted_y & 0xFF

    return bytes(shifted)
