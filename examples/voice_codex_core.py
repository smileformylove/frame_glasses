import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple


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
    if getattr(args, "codex_full_auto", False):
        command.insert(2, "--full-auto")
    if getattr(args, "codex_ephemeral", False):
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
        return args.compact_text(output or f"doctor exit {code}"), False
    if intent.action == "scan":
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "scan"], repo, args.dry_run)
        return args.compact_text(output or f"scan exit {code}"), False
    if intent.action == "pair_test":
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "pair-test", "--", "--text", "Hello from voice bridge"], repo, args.dry_run)
        return args.compact_text(output or f"pair-test exit {code}"), False
    if intent.action == "list_tasks":
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "task-board", "--", "list"], repo, args.dry_run)
        return args.compact_text(output or f"task list exit {code}"), False
    if intent.action == "pin_next_task":
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "task-board", "--", "pin-next"], repo, args.dry_run)
        return args.compact_text(output or f"pin-next exit {code}"), False
    if intent.action == "git_status":
        code, output = await run_shell_text("git status --short --branch", repo, args.dry_run)
        return args.compact_text(output or f"git status exit {code}"), False
    if intent.action == "run_tests":
        code, output = await run_shell_text(args.test_command, repo, args.dry_run)
        label = "tests passed" if code == 0 else f"tests failed ({code})"
        detail = args.compact_text(output or label)
        return detail, False
    if intent.action == "codex_exec":
        code, output = await run_codex_exec(args, intent.payload or "")
        label = output or f"codex exit {code}"
        return args.compact_text(f"CODEX {label}"), False

    return "VOICE CODEX unsupported action.", False
