import argparse
import asyncio
import json
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Deque, Optional

from frame_utils import FrameDisplay, FrameUnicodeDisplay, compact_text, resolve_unicode_font


DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"
DEFAULT_URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"
DEFAULT_RESTORE_DELAY = 1.5


@dataclass
class Notification:
    text: str
    prefix: str = "AGENT"
    level: str = "info"
    source: str = "local"
    timestamp: float = 0.0
    sticky: bool = False
    clear: bool = False


class NotificationDisplay:
    def __init__(
        self,
        name: Optional[str],
        dry_run: bool,
        render_mode: str,
        font_family: Optional[str],
        font_size: int,
        display_width: int,
        max_rows: int,
        limit: int,
    ) -> None:
        self.limit = limit
        use_unicode = render_mode == "unicode" or (render_mode == "auto" and resolve_unicode_font(font_family) is not None)
        if use_unicode:
            self.display = FrameUnicodeDisplay(
                name=name,
                dry_run=dry_run,
                font_family=font_family,
                font_size=font_size,
                display_width=display_width,
                max_rows=max_rows,
            )
            self.unicode_mode = True
        else:
            self.display = FrameDisplay(name=name, dry_run=dry_run)
            self.unicode_mode = False

    async def connect(self) -> None:
        await self.display.connect()

    async def disconnect(self) -> None:
        await self.display.disconnect()

    async def show(self, text: str, x: int = 1, y: int = 1) -> None:
        rendered = text if self.unicode_mode else compact_text(text, self.limit)
        await self.display.show_text(rendered, x=x, y=y)


class AgentHudServer:
    def __init__(
        self,
        host: str,
        port: int,
        display: NotificationDisplay,
        x: int,
        y: int,
        dedupe_window: float,
        recent_limit: int,
        restore_delay: float,
    ) -> None:
        self.host = host
        self.port = port
        self.display = display
        self.x = x
        self.y = y
        self.dedupe_window = dedupe_window
        self.restore_delay = restore_delay
        self.recent: Deque[Notification] = deque(maxlen=recent_limit)
        self.queue: "queue.Queue[Notification]" = queue.Queue()
        self.last_rendered_text = ""
        self.last_render_time = 0.0
        self.pinned_notification: Optional[Notification] = None
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start_http_server(self) -> None:
        handler = self._build_handler()
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop_http_server(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None

    def enqueue(self, notification: Notification) -> None:
        if not notification.timestamp:
            notification.timestamp = time.time()
        self.recent.append(notification)
        self.queue.put(notification)

    def _build_handler(self):
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def _write_json(self, payload, status=200):
                encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_GET(self):
                if self.path == "/health":
                    self._write_json({
                        "ok": True,
                        "queued": parent.queue.qsize(),
                        "recent": len(parent.recent),
                        "pinned": asdict(parent.pinned_notification) if parent.pinned_notification else None,
                    })
                    return
                if self.path == "/recent":
                    self._write_json([asdict(item) for item in list(parent.recent)])
                    return
                if self.path == "/pinned":
                    self._write_json(asdict(parent.pinned_notification) if parent.pinned_notification else None)
                    return
                self._write_json({"error": "not found"}, status=404)

            def do_POST(self):
                if self.path not in ("/notify", "/pin", "/clear"):
                    self._write_json({"error": "not found"}, status=404)
                    return

                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                raw = self.rfile.read(length)
                content_type = self.headers.get("Content-Type", "")

                try:
                    if self.path == "/clear":
                        notification = Notification(text="", clear=True, timestamp=time.time())
                    elif "application/json" in content_type:
                        body = json.loads(raw.decode("utf-8") or "{}")
                        notification = Notification(
                            text=str(body.get("text", "")).strip(),
                            prefix=str(body.get("prefix", "AGENT")).strip() or "AGENT",
                            level=str(body.get("level", "info")).strip() or "info",
                            source=str(body.get("source", "local")).strip() or "local",
                            timestamp=time.time(),
                            sticky=bool(body.get("sticky", False)) or self.path == "/pin",
                        )
                    else:
                        notification = Notification(
                            text=raw.decode("utf-8").strip(),
                            timestamp=time.time(),
                            sticky=self.path == "/pin",
                        )
                except Exception as exc:
                    self._write_json({"error": f"invalid payload: {exc}"}, status=400)
                    return

                if not notification.clear and not notification.text:
                    self._write_json({"error": "text is required"}, status=400)
                    return

                parent.enqueue(notification)
                self._write_json({"ok": True, "queued": parent.queue.qsize()})

            def log_message(self, format, *args):
                _ = format, args

        return Handler

    async def run(self) -> None:
        await self.display.connect()
        await self.display.show(f"AGENT HUD ready on {self.host}:{self.port}", x=self.x, y=self.y)
        self.start_http_server()
        try:
            while True:
                notification = await asyncio.to_thread(self.queue.get)
                if notification.clear:
                    self.pinned_notification = None
                    await self._render("AGENT INFO Cleared pinned message", force=True)
                    continue

                if notification.sticky:
                    self.pinned_notification = notification
                    await self._render(format_notification(notification, sticky=True), force=True)
                    continue

                message = format_notification(notification)
                await self._render(message)
                if self.pinned_notification is not None:
                    await asyncio.sleep(self.restore_delay)
                    await self._render(format_notification(self.pinned_notification, sticky=True), force=True)
        finally:
            self.stop_http_server()
            await self.display.disconnect()

    async def _render(self, message: str, force: bool = False) -> None:
        if not force and should_skip_duplicate(message, self.last_rendered_text, self.last_render_time, self.dedupe_window):
            return
        print(f"[agent-hud] {message}")
        await self.display.show(message, x=self.x, y=self.y)
        self.last_rendered_text = message
        self.last_render_time = time.time()


def format_notification(notification: Notification, sticky: bool = False) -> str:
    level = notification.level.lower()
    level_prefix = {
        "info": "INFO",
        "ok": "OK",
        "success": "OK",
        "warn": "WARN",
        "warning": "WARN",
        "error": "ERROR",
        "fail": "FAIL",
    }.get(level, level.upper() if level else "INFO")
    sticky_prefix = "PIN " if sticky else ""
    return f"{sticky_prefix}{notification.prefix} {level_prefix} {notification.text}".strip()


def should_skip_duplicate(message: str, last_message: str, last_time: float, window: float) -> bool:
    return bool(last_message) and message == last_message and (time.time() - last_time) < window


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Persistent Agent HUD notification service for Frame")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the local notification server and keep Frame connected")
    serve.add_argument("--name", help="Optional BLE device name such as 'Frame 4F'", default=None)
    serve.add_argument("--host", default=DEFAULT_HOST, help="Listen host")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT, help="Listen port")
    serve.add_argument("--dry-run", action="store_true", help="Print notifications locally instead of sending them to Frame")
    serve.add_argument("--render-mode", choices=("auto", "plain", "unicode"), default="auto", help="Notification rendering mode")
    serve.add_argument("--font-family", default=None, help="Optional font path for unicode rendering")
    serve.add_argument("--font-size", type=int, default=28, help="Unicode notification font size")
    serve.add_argument("--display-width", type=int, default=600, help="Unicode notification layout width")
    serve.add_argument("--max-rows", type=int, default=3, help="Maximum unicode notification rows")
    serve.add_argument("--limit", type=int, default=90, help="Maximum plain-text notification length")
    serve.add_argument("--x", type=int, default=1, help="Display x coordinate")
    serve.add_argument("--y", type=int, default=1, help="Display y coordinate")
    serve.add_argument("--dedupe-window", type=float, default=3.0, help="Seconds to suppress identical consecutive notifications")
    serve.add_argument("--recent-limit", type=int, default=50, help="How many recent notifications are kept in memory")
    serve.add_argument("--restore-delay", type=float, default=DEFAULT_RESTORE_DELAY, help="Seconds before re-showing the pinned message after a transient notification")

    send = subparsers.add_parser("send", help="Send a notification to a running Agent HUD server")
    send.add_argument("--url", default=f"{DEFAULT_URL}/notify", help="Notification endpoint URL")
    send.add_argument("--text", required=True, help="Notification text")
    send.add_argument("--prefix", default="AGENT", help="Notification prefix")
    send.add_argument("--level", default="info", help="Notification level such as info, ok, warn, error")
    send.add_argument("--source", default="local", help="Notification source label")

    pin = subparsers.add_parser("pin", help="Pin a sticky notification until cleared")
    pin.add_argument("--url", default=f"{DEFAULT_URL}/pin", help="Pinned notification endpoint URL")
    pin.add_argument("--text", required=True, help="Pinned notification text")
    pin.add_argument("--prefix", default="AGENT", help="Notification prefix")
    pin.add_argument("--level", default="info", help="Notification level such as info, ok, warn, error")
    pin.add_argument("--source", default="local", help="Notification source label")

    clear = subparsers.add_parser("clear", help="Clear the pinned notification")
    clear.add_argument("--url", default=f"{DEFAULT_URL}/clear", help="Clear endpoint URL")

    health = subparsers.add_parser("health", help="Query Agent HUD health information")
    health.add_argument("--url", default=f"{DEFAULT_URL}/health", help="Health endpoint URL")

    recent = subparsers.add_parser("recent", help="Query recent Agent HUD notifications")
    recent.add_argument("--url", default=f"{DEFAULT_URL}/recent", help="Recent notifications endpoint URL")

    pinned = subparsers.add_parser("pinned", help="Query the current pinned notification")
    pinned.add_argument("--url", default=f"{DEFAULT_URL}/pinned", help="Pinned notification endpoint URL")

    demo = subparsers.add_parser("demo", help="Run a local demo by sending sample notifications")
    demo.add_argument("--url", default=DEFAULT_URL, help="Base service URL without the endpoint suffix")
    demo.add_argument("--prefix", default="AGENT", help="Notification prefix")

    pipe = subparsers.add_parser("pipe", help="Read stdin lines and send them as notifications")
    pipe.add_argument("--url", default=f"{DEFAULT_URL}/notify", help="Notification endpoint URL")
    pipe.add_argument("--prefix", default="AGENT", help="Notification prefix")
    pipe.add_argument("--level", default="info", help="Notification level for each stdin line")
    pipe.add_argument("--source", default="stdin", help="Notification source label")

    watch = subparsers.add_parser("watch", help="Poll a command and notify when its output changes")
    watch.add_argument("--url", default=f"{DEFAULT_URL}/notify", help="Notification endpoint URL")
    watch.add_argument("--prefix", default="WATCH", help="Notification prefix")
    watch.add_argument("--source", default="watch", help="Notification source label")
    watch.add_argument("--name", default=None, help="Optional label for the watched command")
    watch.add_argument("--interval", type=float, default=5.0, help="Seconds between polls")
    watch.add_argument("--max-text", type=int, default=140, help="Maximum notification text length")
    watch.add_argument("--pin-latest", action="store_true", help="Pin the latest changed output until the next change")
    watch.add_argument("--clear-pin-on-exit", action="store_true", help="Clear the pinned output when watch exits")
    watch.add_argument("--iterations", type=int, default=0, help="Stop after N iterations, 0 means run forever")
    watch.add_argument("--cwd", default=None, help="Optional working directory for the child command")
    watch.add_argument("watch_command", nargs=argparse.REMAINDER, help="Command to run, place it after --")

    tail = subparsers.add_parser("tail", help="Follow a file and send newly appended lines as notifications")
    tail.add_argument("path", help="File path to follow")
    tail.add_argument("--url", default=f"{DEFAULT_URL}/notify", help="Notification endpoint URL")
    tail.add_argument("--prefix", default="TAIL", help="Notification prefix")
    tail.add_argument("--level", default="info", help="Notification level for tailed lines")
    tail.add_argument("--source", default="tail", help="Notification source label")
    tail.add_argument("--poll-interval", type=float, default=0.5, help="Seconds between file checks")
    tail.add_argument("--from-start", action="store_true", help="Read the file from the start instead of only new lines")
    tail.add_argument("--max-lines", type=int, default=0, help="Stop after sending N lines, 0 means unlimited")

    return parser


def post_json(url: str, payload: dict) -> None:
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to contact Agent HUD: {exc}") from exc
    print(body)


def pin_url(url: str) -> str:
    return url[:-7] + "/pin" if url.endswith("/notify") else url.rstrip("/") + "/pin"


def clear_url(url: str) -> str:
    return url[:-7] + "/clear" if url.endswith("/notify") else url.rstrip("/") + "/clear"


def send_notification(url: str, text: str, prefix: str, level: str, source: str, sticky: bool = False) -> None:
    post_json(url, {
        "text": text,
        "prefix": prefix,
        "level": level,
        "source": source,
        "sticky": sticky,
    })


def clear_notification(url: str) -> None:
    post_json(url, {})


def get_json(url: str) -> None:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            print(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to query Agent HUD: {exc}") from exc


async def run_demo(base_url: str, prefix: str) -> None:
    samples = [
        ("Starting repo checks", "info"),
        ("Tests passed", "ok"),
        ("Deploy warning: staging only", "warn"),
        ("Build failed on integration step", "error"),
    ]
    send_notification(f"{base_url}/pin", "Pinned sprint focus: stabilize BLE", prefix, "info", "demo", sticky=True)
    await asyncio.sleep(0.1)
    for text, level in samples:
        send_notification(f"{base_url}/notify", text, prefix, level, "demo")
        await asyncio.sleep(0.1)
    clear_notification(f"{base_url}/clear")


def pipe_notifications(url: str, prefix: str, level: str, source: str) -> None:
    for raw_line in sys.stdin:
        text = raw_line.strip()
        if not text:
            continue
        send_notification(url, text, prefix, level, source)


async def run_watch(args) -> None:
    command = args.watch_command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("A command is required after --")

    last_summary = None
    iteration = 0
    while True:
        iteration += 1
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=args.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        output = (stdout + stderr).decode(errors="replace").strip()
        summary = compact_text(" ".join(output.split()) or f"exit {process.returncode} (no output)", args.max_text)
        if args.name:
            summary = compact_text(f"{args.name}: {summary}", args.max_text)
        changed = summary != last_summary
        if changed:
            level = "error" if process.returncode != 0 else "info"
            send_notification(args.url, summary, args.prefix, level, args.source)
            if args.pin_latest:
                send_notification(pin_url(args.url), summary, args.prefix, level, args.source, sticky=True)
            last_summary = summary
        if args.iterations and iteration >= args.iterations:
            break
        await asyncio.sleep(args.interval)

    if args.clear_pin_on_exit:
        clear_notification(clear_url(args.url))


async def run_tail(args) -> None:
    path = Path(args.path).expanduser()
    while not path.exists():
        print(f"[agent-hud] waiting for file: {path}")
        await asyncio.sleep(args.poll_interval)

    sent = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        if not args.from_start:
            handle.seek(0, 2)

        while True:
            line = handle.readline()
            if not line:
                await asyncio.sleep(args.poll_interval)
                continue

            text = line.strip()
            if not text:
                continue

            send_notification(args.url, text, args.prefix, args.level, args.source)
            sent += 1
            if args.max_lines and sent >= args.max_lines:
                break


async def async_main() -> None:
    args = build_parser().parse_args()
    if args.command == "send":
        send_notification(args.url, args.text, args.prefix, args.level, args.source)
        return
    if args.command == "pin":
        send_notification(args.url, args.text, args.prefix, args.level, args.source, sticky=True)
        return
    if args.command == "clear":
        clear_notification(args.url)
        return
    if args.command == "health":
        get_json(args.url)
        return
    if args.command == "recent":
        get_json(args.url)
        return
    if args.command == "pinned":
        get_json(args.url)
        return
    if args.command == "demo":
        await run_demo(args.url, args.prefix)
        return
    if args.command == "pipe":
        pipe_notifications(args.url, args.prefix, args.level, args.source)
        return
    if args.command == "watch":
        await run_watch(args)
        return
    if args.command == "tail":
        await run_tail(args)
        return
    if args.command == "serve":
        display = NotificationDisplay(
            name=args.name,
            dry_run=args.dry_run,
            render_mode=args.render_mode,
            font_family=args.font_family,
            font_size=args.font_size,
            display_width=args.display_width,
            max_rows=args.max_rows,
            limit=args.limit,
        )
        server = AgentHudServer(
            host=args.host,
            port=args.port,
            display=display,
            x=args.x,
            y=args.y,
            dedupe_window=args.dedupe_window,
            recent_limit=args.recent_limit,
            restore_delay=args.restore_delay,
        )
        await server.run()
        return
    raise ValueError(f"Unsupported command: {args.command}")


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nAgent HUD stopped.")


if __name__ == "__main__":
    main()
