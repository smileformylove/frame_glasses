import argparse
import asyncio
import json
import re
import sys
import urllib.error
import urllib.request
from typing import Iterable, Optional


KEYWORDS = (
    "error",
    "failed",
    "failure",
    "warn",
    "warning",
    "success",
    "passed",
    "exception",
    "traceback",
)
DEFAULT_URL = "http://127.0.0.1:8765/notify"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a command and emit Agent HUD notifications for start, important lines, and exit status")
    parser.add_argument("--url", default=DEFAULT_URL, help="Agent HUD notification endpoint URL")
    parser.add_argument("--prefix", default="RUN", help="Notification prefix")
    parser.add_argument("--source", default="notify-run", help="Notification source label")
    parser.add_argument("--name", default=None, help="Optional human-readable name for the command")
    parser.add_argument("--notify-every", type=int, default=5, help="Also notify every Nth output line")
    parser.add_argument("--max-text", type=int, default=140, help="Maximum notification text length")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run, place it after --")
    return parser


def compact_text(text: str, limit: int) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: max(0, limit - 1)] + "…"


def should_notify(line: str, line_count: int, every: int) -> bool:
    lowered = line.lower()
    return any(keyword in lowered for keyword in KEYWORDS) or line_count == 1 or (every > 0 and line_count % every == 0)


def send_notification(url: str, text: str, prefix: str, level: str, source: str) -> None:
    payload = json.dumps(
        {
            "text": text,
            "prefix": prefix,
            "level": level,
            "source": source,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5):
            return
    except urllib.error.URLError as exc:
        print(f"[notify-run] failed to send notification: {exc}", file=sys.stderr)


async def pump_stream(stream: asyncio.StreamReader, label: str, notifier) -> None:
    line_count = 0
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode(errors="replace").rstrip()
        if not text:
            continue
        print(f"[{label}] {text}")
        line_count += 1
        await notifier(text, line_count, label)


async def run_command(args) -> int:
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("A command is required after --")

    command_name = args.name or " ".join(command)
    send_notification(args.url, compact_text(f"Starting {command_name}", args.max_text), args.prefix, "info", args.source)

    last_sent: Optional[str] = None

    async def notifier(text: str, line_count: int, label: str) -> None:
        nonlocal last_sent
        if not should_notify(text, line_count, args.notify_every):
            return
        level = infer_level(text)
        message = compact_text(f"{label} {text}", args.max_text)
        if message == last_sent:
            return
        send_notification(args.url, message, args.prefix, level, args.source)
        last_sent = message

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    tasks = [
        asyncio.create_task(pump_stream(process.stdout, "OUT", notifier)),
        asyncio.create_task(pump_stream(process.stderr, "ERR", notifier)),
    ]

    return_code = await process.wait()
    await asyncio.gather(*tasks)

    if return_code == 0:
        send_notification(args.url, compact_text(f"Finished {command_name}", args.max_text), args.prefix, "ok", args.source)
    else:
        send_notification(args.url, compact_text(f"Failed {command_name} (exit {return_code})", args.max_text), args.prefix, "error", args.source)
    return return_code


def infer_level(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("error", "failed", "failure", "exception", "traceback")):
        return "error"
    if any(token in lowered for token in ("warn", "warning")):
        return "warn"
    if any(token in lowered for token in ("success", "passed")):
        return "ok"
    return "info"


def main() -> None:
    args = build_parser().parse_args()
    try:
        return_code = asyncio.run(run_command(args))
    except KeyboardInterrupt:
        return_code = 130
    raise SystemExit(return_code)


if __name__ == "__main__":
    main()
