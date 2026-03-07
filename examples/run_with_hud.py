import argparse
import asyncio
import os
from typing import Optional

from frame_utils import FrameDisplay, compact_text, sleep_briefly


KEYWORDS = (
    "error",
    "failed",
    "success",
    "warning",
    "warn",
    "passed",
    "exception",
    "traceback",
)


async def pump_stream(stream: asyncio.StreamReader, label: str, queue: asyncio.Queue) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode(errors="replace").rstrip()
        if text:
            print(f"[{label}] {text}")
            await queue.put((label, text))


async def forward_updates(
    display: FrameDisplay,
    queue: asyncio.Queue,
    prefix: str,
    x: int,
    y: int,
    limit: int,
) -> None:
    last_sent: Optional[str] = None
    line_count = 0

    while True:
        item = await queue.get()
        if item is None:
            break

        label, text = item
        line_count += 1
        lowered = text.lower()
        should_send = any(keyword in lowered for keyword in KEYWORDS) or line_count == 1 or line_count % 5 == 0
        if not should_send:
            continue

        rendered = compact_text(f"{prefix} {label} {text}".strip(), limit)
        if rendered == last_sent:
            continue

        await display.show_text(rendered, x=x, y=y)
        last_sent = rendered
        await sleep_briefly()


async def run_command(
    name: Optional[str],
    prefix: str,
    x: int,
    y: int,
    limit: int,
    cwd: Optional[str],
    dry_run: bool,
    command: list[str],
) -> int:
    if not command:
        raise ValueError("A command is required after --")

    display = FrameDisplay(name=name, dry_run=dry_run)
    queue: asyncio.Queue = asyncio.Queue()
    command_preview = " ".join(command)
    run_cwd = cwd or os.getcwd()

    await display.connect()
    await display.show_text(compact_text(f"RUN {command_preview}", limit), x=x, y=y)

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=run_cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        tasks = [
            asyncio.create_task(pump_stream(process.stdout, "OUT", queue)),
            asyncio.create_task(pump_stream(process.stderr, "ERR", queue)),
            asyncio.create_task(forward_updates(display, queue, prefix, x, y, limit)),
        ]

        return_code = await process.wait()
        await tasks[0]
        await tasks[1]
        await queue.put(None)
        await tasks[2]

        for task in tasks:
            if not task.done():
                task.cancel()

        status = "OK" if return_code == 0 else f"FAIL {return_code}"
        await display.show_text(compact_text(f"{prefix} {status}".strip(), limit), x=x, y=y)
        return return_code
    finally:
        await display.disconnect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a command and mirror useful output to Brilliant Labs Frame")
    parser.add_argument("--name", help="Optional BLE device name", default=None)
    parser.add_argument("--prefix", help="Optional display prefix", default="DEV")
    parser.add_argument("--x", type=int, default=1, help="Display x coordinate")
    parser.add_argument("--y", type=int, default=1, help="Display y coordinate")
    parser.add_argument("--limit", type=int, default=80, help="Maximum displayed characters per line")
    parser.add_argument("--cwd", help="Working directory for the child command", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print locally instead of connecting to Frame")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run, place it after --")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]

    try:
        return_code = asyncio.run(
            run_command(
                args.name,
                args.prefix,
                args.x,
                args.y,
                args.limit,
                args.cwd,
                args.dry_run,
                command,
            )
        )
    except KeyboardInterrupt:
        return_code = 130

    raise SystemExit(return_code)


if __name__ == "__main__":
    main()
