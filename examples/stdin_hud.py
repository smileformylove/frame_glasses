import argparse
import asyncio
import sys
from typing import Optional

from frame_utils import FrameDisplay, compact_text


async def run(name: Optional[str], prefix: str, x: int, y: int, limit: int, dry_run: bool) -> None:
    display = FrameDisplay(name=name, dry_run=dry_run)
    await display.connect()
    try:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue

            rendered = compact_text(f"{prefix} {line}".strip(), limit)
            await display.show_text(rendered, x=x, y=y)
    finally:
        await display.disconnect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mirror stdin lines to Brilliant Labs Frame")
    parser.add_argument("--name", help="Optional BLE device name", default=None)
    parser.add_argument("--prefix", help="Optional text prefix", default="")
    parser.add_argument("--x", type=int, default=1, help="Display x coordinate")
    parser.add_argument("--y", type=int, default=1, help="Display y coordinate")
    parser.add_argument("--limit", type=int, default=80, help="Maximum displayed characters per line")
    parser.add_argument("--dry-run", action="store_true", help="Print locally instead of connecting to Frame")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        asyncio.run(run(args.name, args.prefix, args.x, args.y, args.limit, args.dry_run))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
