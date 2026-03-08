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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Deque, Optional

from frame_utils import FrameDisplay, FrameUnicodeDisplay, compact_text, resolve_unicode_font


DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"
DEFAULT_URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/notify"


@dataclass
class Notification:
    text: str
    prefix: str = "AGENT"
    level: str = "info"
    source: str = "local"
    timestamp: float = 0.0


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
    ) -> None:
        self.host = host
        self.port = port
        self.display = display
        self.x = x
        self.y = y
        self.dedupe_window = dedupe_window
        self.recent: Deque[Notification] = deque(maxlen=recent_limit)
        self.queue: "queue.Queue[Notification]" = queue.Queue()
        self.last_rendered_text = ""
        self.last_render_time = 0.0
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
                    self._write_json({"ok": True, "queued": parent.queue.qsize(), "recent": len(parent.recent)})
                    return
                if self.path == "/recent":
                    self._write_json([asdict(item) for item in list(parent.recent)])
                    return
                self._write_json({"error": "not found"}, status=404)

            def do_POST(self):
                if self.path != "/notify":
                    self._write_json({"error": "not found"}, status=404)
                    return

                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                raw = self.rfile.read(length)
                content_type = self.headers.get("Content-Type", "")

                try:
                    if "application/json" in content_type:
                        body = json.loads(raw.decode("utf-8") or "{}")
                        notification = Notification(
                            text=str(body.get("text", "")).strip(),
                            prefix=str(body.get("prefix", "AGENT")).strip() or "AGENT",
                            level=str(body.get("level", "info")).strip() or "info",
                            source=str(body.get("source", "local")).strip() or "local",
                            timestamp=time.time(),
                        )
                    else:
                        notification = Notification(text=raw.decode("utf-8").strip(), timestamp=time.time())
                except Exception as exc:
                    self._write_json({"error": f"invalid payload: {exc}"}, status=400)
                    return

                if not notification.text:
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
                message = format_notification(notification)
                if should_skip_duplicate(message, self.last_rendered_text, self.last_render_time, self.dedupe_window):
                    continue
                print(f"[agent-hud] {message}")
                await self.display.show(message, x=self.x, y=self.y)
                self.last_rendered_text = message
                self.last_render_time = time.time()
        finally:
            self.stop_http_server()
            await self.display.disconnect()


def format_notification(notification: Notification) -> str:
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
    return f"{notification.prefix} {level_prefix} {notification.text}".strip()


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

    send = subparsers.add_parser("send", help="Send a notification to a running Agent HUD server")
    send.add_argument("--url", default=DEFAULT_URL, help="Notification endpoint URL")
    send.add_argument("--text", required=True, help="Notification text")
    send.add_argument("--prefix", default="AGENT", help="Notification prefix")
    send.add_argument("--level", default="info", help="Notification level such as info, ok, warn, error")
    send.add_argument("--source", default="local", help="Notification source label")

    demo = subparsers.add_parser("demo", help="Run a local demo by sending sample notifications")
    demo.add_argument("--url", default=DEFAULT_URL, help="Notification endpoint URL")
    demo.add_argument("--prefix", default="AGENT", help="Notification prefix")

    pipe = subparsers.add_parser("pipe", help="Read stdin lines and send them as notifications")
    pipe.add_argument("--url", default=DEFAULT_URL, help="Notification endpoint URL")
    pipe.add_argument("--prefix", default="AGENT", help="Notification prefix")
    pipe.add_argument("--level", default="info", help="Notification level for each stdin line")
    pipe.add_argument("--source", default="stdin", help="Notification source label")

    return parser


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
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to send notification: {exc}") from exc
    print(body)


async def run_demo(url: str, prefix: str) -> None:
    samples = [
        ("Starting repo checks", "info"),
        ("Tests passed", "ok"),
        ("Deploy warning: staging only", "warn"),
        ("Build failed on integration step", "error"),
    ]
    for text, level in samples:
        send_notification(url, text, prefix, level, "demo")
        await asyncio.sleep(0.1)


def pipe_notifications(url: str, prefix: str, level: str, source: str) -> None:
    for raw_line in sys.stdin:
        text = raw_line.strip()
        if not text:
            continue
        send_notification(url, text, prefix, level, source)


async def async_main() -> None:
    args = build_parser().parse_args()
    if args.command == "send":
        send_notification(args.url, args.text, args.prefix, args.level, args.source)
        return
    if args.command == "demo":
        await run_demo(args.url, args.prefix)
        return
    if args.command == "pipe":
        pipe_notifications(args.url, args.prefix, args.level, args.source)
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
