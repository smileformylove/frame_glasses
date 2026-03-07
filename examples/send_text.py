import argparse
import asyncio
from typing import Optional

from frame_utils import FrameDisplay


async def show_text(name: Optional[str], text: str, x: int, y: int, dry_run: bool) -> None:
    display = FrameDisplay(name=name, dry_run=dry_run)
    await display.connect()
    try:
        await display.show_text(text, x=x, y=y)
    finally:
        await display.disconnect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send one line of text to Brilliant Labs Frame")
    parser.add_argument("--name", help="Optional BLE device name", default=None)
    parser.add_argument("--text", help="Text to display on Frame", required=True)
    parser.add_argument("--x", type=int, default=1, help="Display x coordinate")
    parser.add_argument("--y", type=int, default=1, help="Display y coordinate")
    parser.add_argument("--dry-run", action="store_true", help="Print locally instead of connecting to Frame")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(show_text(args.name, args.text, args.x, args.y, args.dry_run))


if __name__ == "__main__":
    main()
