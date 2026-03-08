import argparse
import asyncio
import subprocess
import sys
import tempfile
from argparse import Namespace
from pathlib import Path
from typing import Optional, Sequence, Tuple

from frame_utils import FrameUnicodeDisplay, compact_text
from meeting_hud import (
    FasterWhisperTranscriber,
    capture_audio_chunk,
    compute_rms,
    list_audio_devices,
    normalize_audio,
    parse_audio_device,
)
from vision_hud import choose_display


DEFAULT_COMMANDS = "help|doctor|scan frame|pair test|git status|list tasks|pin next task|run tests|ask codex summarize the repo|exit"
DEFAULT_HELP_TEXT = "VOICE CODEX help: doctor, scan, pair test, git status, list tasks, pin next task, run tests, ask codex ..., exit"
EXIT_WORDS = ("exit", "quit", "stop", "结束", "退出", "停止")
HELP_WORDS = ("help", "what can you do", "commands", "帮助")
DOCTOR_WORDS = ("doctor", "check environment", "环境检查", "检查环境")
SCAN_WORDS = ("scan frame", "scan device", "扫描眼镜", "扫描设备")
PAIR_TEST_WORDS = ("pair test", "test connection", "连接测试", "配对测试")
GIT_STATUS_WORDS = ("git status", "status", "git 状态")
LIST_TASKS_WORDS = ("list tasks", "show tasks", "任务列表", "列任务")
PIN_NEXT_TASK_WORDS = ("pin next task", "focus task", "pin task", "置顶任务", "下一任务")
RUN_TESTS_WORDS = ("run tests", "run test", "运行测试", "测试一下")
CODEX_PREFIXES = ("ask codex ", "codex ", "让 codex ", "请 codex ")


class BridgeIntent:
    def __init__(self, action: str, payload: Optional[str] = None, raw: str = ""):
        self.action = action
        self.payload = payload
        self.raw = raw


class ResultDisplay:
    def __init__(self, args):
        self.args = args

    async def show(self, text: str) -> None:
        display = choose_display(self.args, text)
        rendered = text if isinstance(display, FrameUnicodeDisplay) else compact_text(text, self.args.limit)
        await display.connect()
        try:
            await display.show_text(rendered, x=self.args.x, y=self.args.y)
        finally:
            await display.disconnect()



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Listen for voice commands and run safe local actions or Codex exec requests")
    parser.add_argument("--name", help="Optional BLE device name such as 'Frame EF'", default=None)
    parser.add_argument("--repo", default=".", help="Repo root used for local commands and Codex exec")
    parser.add_argument("--dry-run", action="store_true", help="Do not run commands; only print what would happen")
    parser.add_argument("--render-mode", choices=("auto", "plain", "unicode"), default="auto", help="Result rendering mode on Frame")
    parser.add_argument("--font-family", default=None, help="Optional font path for unicode rendering")
    parser.add_argument("--font-size", type=int, default=28, help="Unicode result font size")
    parser.add_argument("--display-width", type=int, default=600, help="Unicode result layout width")
    parser.add_argument("--max-rows", type=int, default=3, help="Maximum unicode result rows")
    parser.add_argument("--x", type=int, default=1, help="Display x coordinate")
    parser.add_argument("--y", type=int, default=1, help="Display y coordinate")
    parser.add_argument("--limit", type=int, default=100, help="Maximum plain-text result length")
    parser.add_argument("--list-devices", action="store_true", help="List audio input devices and exit")
    parser.add_argument("--audio-device", help="Audio device index or name", default=None)
    parser.add_argument("--listen-duration", type=float, default=3.0, help="Seconds recorded per voice command attempt")
    parser.add_argument("--samplerate", type=int, default=16000, help="Audio sample rate")
    parser.add_argument("--min-rms", type=float, default=0.015, help="Silence threshold for command audio")
    parser.add_argument("--model", default="base", help="faster-whisper model name")
    parser.add_argument("--language", default=None, help="Optional spoken command language code such as en or zh")
    parser.add_argument("--device", default="auto", help="Whisper device, usually auto or cpu on macOS")
    parser.add_argument("--compute-type", default="int8", help="Whisper compute type")
    parser.add_argument("--beam-size", type=int, default=1, help="Whisper beam size")
    parser.add_argument("--test-command", default="pytest -q", help="Shell command used for the 'run tests' voice action")
    parser.add_argument("--codex-bin", default="codex", help="Path to the Codex CLI executable")
    parser.add_argument("--codex-sandbox", default="workspace-write", help="Sandbox mode used for codex exec")
    parser.add_argument("--codex-full-auto", action="store_true", help="Pass --full-auto to codex exec")
    parser.add_argument("--codex-ephemeral", action="store_true", help="Pass --ephemeral to codex exec")
    parser.add_argument("--demo", action="store_true", help="Run a local demo without using the microphone")
    parser.add_argument("--demo-commands", default=DEFAULT_COMMANDS, help="Pipe-separated command phrases used in demo mode")
    return parser


def parse_intent(text: str) -> BridgeIntent:
    lowered = text.lower().strip()
    if not lowered:
        return BridgeIntent("unknown", raw=text)
    if any(word in lowered for word in EXIT_WORDS):
        return BridgeIntent("exit", raw=text)
    if any(word in lowered for word in HELP_WORDS):
        return BridgeIntent("help", raw=text)
    if any(word in lowered for word in DOCTOR_WORDS):
        return BridgeIntent("doctor", raw=text)
    if any(word in lowered for word in SCAN_WORDS):
        return BridgeIntent("scan", raw=text)
    if any(word in lowered for word in PAIR_TEST_WORDS):
        return BridgeIntent("pair_test", raw=text)
    if any(word in lowered for word in PIN_NEXT_TASK_WORDS):
        return BridgeIntent("pin_next_task", raw=text)
    if any(word in lowered for word in LIST_TASKS_WORDS):
        return BridgeIntent("list_tasks", raw=text)
    if any(word in lowered for word in RUN_TESTS_WORDS):
        return BridgeIntent("run_tests", raw=text)
    if any(word in lowered for word in GIT_STATUS_WORDS):
        return BridgeIntent("git_status", raw=text)
    for prefix in CODEX_PREFIXES:
        if lowered.startswith(prefix):
            return BridgeIntent("codex_exec", payload=text[len(prefix):].strip(), raw=text)
    return BridgeIntent("unknown", raw=text)


async def run_subprocess(command: list[str], cwd: Path, dry_run: bool) -> Tuple[int, str]:
    if dry_run:
        return 0, f"DRY RUN: {' '.join(command)}"

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    output = (stdout + stderr).decode(errors="replace").strip()
    return process.returncode, output


async def run_shell_text(command_text: str, cwd: Path, dry_run: bool) -> Tuple[int, str]:
    command = ["/bin/zsh", "-lc", command_text]
    return await run_subprocess(command, cwd, dry_run)


async def run_codex_exec(args, prompt: str) -> Tuple[int, str]:
    if not prompt:
        return 1, "VOICE CODEX missing prompt after 'ask codex'"

    repo = Path(args.repo).expanduser().resolve()
    with tempfile.NamedTemporaryFile(prefix="voice_codex_", suffix=".txt", delete=False) as handle:
        output_file = Path(handle.name)

    command = [
        args.codex_bin,
        "exec",
        "--cd",
        str(repo),
        "--sandbox",
        args.codex_sandbox,
        "--output-last-message",
        str(output_file),
        prompt,
    ]
    if args.codex_full_auto:
        command.insert(2, "--full-auto")
    if args.codex_ephemeral:
        command.insert(2, "--ephemeral")

    code, output = await run_subprocess(command, repo, args.dry_run)
    if args.dry_run:
        return code, output

    final_text = output_file.read_text(encoding="utf-8", errors="replace").strip() if output_file.exists() else ""
    output_file.unlink(missing_ok=True)
    summary = final_text or output or "Codex returned no message"
    return code, summary


async def execute_intent(args, intent: BridgeIntent) -> Tuple[str, bool]:
    repo = Path(args.repo).expanduser().resolve()
    if intent.action == "help":
        return DEFAULT_HELP_TEXT, False
    if intent.action == "exit":
        return "VOICE CODEX stopping", True
    if intent.action == "unknown":
        return "VOICE CODEX unknown command. Say help.", False

    if intent.action == "doctor":
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "doctor"], repo, args.dry_run)
        return compact_text(output or f"doctor exit {code}", args.limit), False
    if intent.action == "scan":
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "scan"], repo, args.dry_run)
        return compact_text(output or f"scan exit {code}", args.limit), False
    if intent.action == "pair_test":
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "pair-test", "--", "--text", "Hello from voice bridge"], repo, args.dry_run)
        return compact_text(output or f"pair-test exit {code}", args.limit), False
    if intent.action == "list_tasks":
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "task-board", "--", "list"], repo, args.dry_run)
        return compact_text(output or f"task list exit {code}", args.limit), False
    if intent.action == "pin_next_task":
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "task-board", "--", "pin-next"], repo, args.dry_run)
        return compact_text(output or f"pin-next exit {code}", args.limit), False
    if intent.action == "git_status":
        code, output = await run_shell_text("git status --short --branch", repo, args.dry_run)
        return compact_text(output or f"git status exit {code}", args.limit), False
    if intent.action == "run_tests":
        code, output = await run_shell_text(args.test_command, repo, args.dry_run)
        label = "tests passed" if code == 0 else f"tests failed ({code})"
        detail = compact_text(output or label, args.limit)
        return detail, False
    if intent.action == "codex_exec":
        code, output = await run_codex_exec(args, intent.payload or "")
        label = output or f"codex exit {code}"
        return compact_text(f"CODEX {label}", args.limit), False

    return "VOICE CODEX unsupported action.", False


async def run_demo(args) -> None:
    display = ResultDisplay(args)
    commands = [part.strip() for part in args.demo_commands.split("|") if part.strip()]
    for command_text in commands:
        print(f"[voice-codex] heard={command_text}")
        intent = parse_intent(command_text)
        try:
            message, should_exit = await execute_intent(args, intent)
        except Exception as exc:
            message, should_exit = f"VOICE CODEX error: {exc}", False
        print(f"[voice-codex] result={message}")
        if not args.dry_run:
            await display.show(message)
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
    display = ResultDisplay(args)
    await display.show("VOICE CODEX ready. Say help, doctor, scan, run tests, ask codex, or exit.")

    while True:
        audio_chunk = await asyncio.to_thread(capture_audio_chunk, args.listen_duration, args.samplerate, parse_audio_device(args.audio_device))
        rms = compute_rms(audio_chunk)
        print(f"[voice-codex] rms={rms:.4f}")
        if rms < args.min_rms:
            continue

        normalized = normalize_audio(audio_chunk)
        text = await asyncio.to_thread(transcriber.transcribe, normalized)
        if not text:
            continue

        print(f"[voice-codex] heard={text}")
        intent = parse_intent(text)
        try:
            message, should_exit = await execute_intent(args, intent)
        except Exception as exc:
            message, should_exit = f"VOICE CODEX error: {exc}", False
        print(f"[voice-codex] result={message}")
        await display.show(message)
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
        print("\nVoice Codex Bridge stopped.")


if __name__ == "__main__":
    main()
