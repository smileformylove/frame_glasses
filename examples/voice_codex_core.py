import difflib
import re
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from command_summary import (
    summarize_codex_output,
    summarize_doctor_output,
    summarize_git_status,
    summarize_pair_test_output,
    summarize_pytest_output,
    summarize_scan_output,
    summarize_task_list_output,
)


DEFAULT_COMMANDS = "help|doctor|scan frame|pair test|git status|list tasks|pin next task|run tests|resume codex|code review|ask codex summarize the repo|repeat|confirm|cancel|exit"
DEFAULT_HELP_TEXT = "VOICE CODEX help: doctor, scan, pair test, git status, list tasks, pin next task, run tests, resume codex, code review, ask codex ..., repeat, confirm, cancel, exit"
EXIT_WORDS = ("exit", "quit", "stop", "结束", "退出", "停止")
FILLER_PREFIXES = ("please ", "can you ", "could you ", "请", "帮我", "麻烦", "现在", "能不能")
HELP_WORDS = ("help", "what can you do", "commands", "帮助")
CONFIRM_WORDS = ("confirm", "yes", "go ahead", "do it", "确认", "执行", "继续执行", "好的")
CANCEL_WORDS = ("cancel", "no", "never mind", "stop that", "取消", "不用了", "算了")
REPEAT_WORDS = ("repeat", "say again", "again", "再说一次", "重复一下", "再来一遍")
DOCTOR_WORDS = ("doctor", "check environment", "环境检查", "检查环境")
SCAN_WORDS = ("scan frame", "scan device", "扫描眼镜", "扫描设备")
PAIR_TEST_WORDS = ("pair test", "test connection", "连接测试", "配对测试")
GIT_STATUS_WORDS = ("git status", "status", "git 状态", "代码状态", "仓库状态")
LIST_TASKS_WORDS = ("list tasks", "show tasks", "任务列表", "列任务", "查看任务", "看看任务")
PIN_NEXT_TASK_WORDS = ("pin next task", "focus task", "pin task", "置顶任务", "下一任务", "聚焦任务", "置顶下一任务")
RUN_TESTS_WORDS = ("run tests", "run test", "运行测试", "测试一下", "跑测试", "执行测试", "开始测试", "做测试")
RESUME_CODEX_WORDS = ("resume codex", "resume last codex", "continue codex", "继续 codex", "继续上次 codex", "继续上次任务")
CODE_REVIEW_WORDS = ("code review", "review code", "review repo", "代码审查", "代码 review", "审查代码", "检查代码")
CODEX_PREFIXES = ("ask codex ", "codex ", "让 codex ", "请 codex ", "让 codex 帮我", "请 codex 帮我")



COMMON_REPLACEMENTS = {
    '状太': '状态',
    '装态': '状态',
    '庄态': '状态',
    'git 装态': 'git 状态',
    'git 状太': 'git 状态',
    '仓库装态': '仓库状态',
    'frane': 'frame',
    'fraem': 'frame',
    'farme': 'frame',
    '测是': '测试',
    '测式': '测试',
    '册试': '测试',
    '跑测是': '跑测试',
    '执行测是': '执行测试',
    'codx': 'codex',
    'codec': 'codex',
    'co d ex': 'codex',
}


def apply_common_replacements(text: str) -> str:
    corrected = text
    for source, target in COMMON_REPLACEMENTS.items():
        corrected = corrected.replace(source, target)
    return corrected


ACTION_PHRASES = {
    "help": ("help", "commands", "帮助", "你能做什么"),
    "doctor": ("doctor", "check environment", "环境检查", "检查环境"),
    "scan": ("scan frame", "scan device", "扫描眼镜", "扫描设备", "扫描 frame"),
    "pair_test": ("pair test", "test connection", "连接测试", "配对测试", "测试连接"),
    "git_status": ("git status", "git 状态", "代码状态", "仓库状态"),
    "list_tasks": ("list tasks", "show tasks", "任务列表", "列任务", "查看任务"),
    "pin_next_task": ("pin next task", "focus task", "置顶任务", "下一任务", "聚焦任务"),
    "run_tests": ("run tests", "运行测试", "跑测试", "执行测试"),
    "codex_resume": ("resume codex", "continue codex", "继续上次任务", "继续上次 codex"),
    "codex_review": ("code review", "review code", "代码审查", "检查代码"),
    "confirm": ("confirm", "确认", "执行", "继续", "好的"),
    "cancel": ("cancel", "取消", "不用了", "算了"),
    "exit": ("exit", "quit", "结束", "退出", "停止"),
}
FUZZY_THRESHOLD = 0.72


def fuzzy_match_action(text: str) -> Optional[str]:
    best_action = None
    best_score = 0.0
    for action, phrases in ACTION_PHRASES.items():
        for phrase in phrases:
            score = difflib.SequenceMatcher(None, text, phrase).ratio()
            if score > best_score:
                best_score = score
                best_action = action
    if best_score >= FUZZY_THRESHOLD:
        return best_action
    return None


def normalize_command_text(text: str) -> str:
    normalized = text.strip().lower()
    normalized = normalized.replace('：', ':').replace('，', ' ').replace('。', ' ').replace('？', ' ').replace('！', ' ')
    normalized = re.sub(r"[\t\n\r]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = apply_common_replacements(normalized)
    for prefix in FILLER_PREFIXES:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
    return normalized


def strip_wake_word(text: str, wake_word: Optional[str]) -> Optional[str]:
    normalized = normalize_command_text(text)
    if not wake_word:
        return normalized
    wake = normalize_command_text(wake_word)
    if normalized == wake:
        return ""
    if normalized.startswith(wake + " "):
        return normalized[len(wake):].strip()
    return None




def locale_for_args(args) -> str:
    language = (getattr(args, 'language', None) or '').lower()
    if language.startswith(('zh', 'ja', 'ko')):
        return 'zh'
    return 'en'


def help_message(locale: str) -> str:
    return DEFAULT_HELP_TEXT if locale == 'en' else '语音 Codex：可说 doctor、scan、pair test、git status、list tasks、pin next task、run tests、ask codex、confirm、cancel、exit'


def stop_message(locale: str) -> str:
    return 'VOICE CODEX stopping' if locale == 'en' else '语音 Codex 已停止'


def unknown_message(locale: str) -> str:
    return 'VOICE CODEX unknown command. Say help.' if locale == 'en' else '语音 Codex 没听懂，请说 help。'


def nothing_pending(locale: str, kind: str) -> str:
    if locale == 'en':
        return f'VOICE CODEX nothing pending to {kind}.'
    return '当前没有待确认操作。'


def canceled_message(locale: str) -> str:
    return 'VOICE CODEX canceled.' if locale == 'en' else '已取消执行。'


def expired_message(locale: str) -> str:
    return 'VOICE CODEX confirmation timed out.' if locale == 'en' else '确认已超时，请重新发出命令。'


def confirmation_prompt(intent: "BridgeIntent", locale: str = 'en') -> str:
    if locale == 'en':
        return f'Confirm {describe_intent(intent)}? Say confirm or cancel.'
    return f'确认执行：{describe_intent(intent)}？请说 confirm 或 cancel。'


def normalize_shortcut_key(text: str) -> str:
    return normalize_command_text(text)


def lookup_shortcut(text: str, shortcuts) -> Optional["BridgeIntent"]:
    if not shortcuts:
        return None
    key = normalize_shortcut_key(text)
    config = shortcuts.get(key)
    if not config:
        return None
    return BridgeIntent(config.get('action', 'unknown'), payload=config.get('payload'), raw=text)


class BridgeIntent:
    def __init__(self, action: str, payload: Optional[str] = None, raw: str = ""):
        self.action = action
        self.payload = payload
        self.raw = raw


def parse_intent(text: str, wake_word: Optional[str] = None, shortcuts=None) -> BridgeIntent:
    lowered = strip_wake_word(text, wake_word)
    if lowered is None:
        return BridgeIntent("ignored", raw=text)
    if lowered == "":
        return BridgeIntent("help", raw=text)
    if not lowered:
        return BridgeIntent("unknown", raw=text)
    shortcut_intent = lookup_shortcut(lowered, shortcuts)
    if shortcut_intent is not None:
        return shortcut_intent
    if any(word in lowered for word in EXIT_WORDS):
        return BridgeIntent("exit", raw=text)
    if any(word in lowered for word in HELP_WORDS):
        return BridgeIntent("help", raw=text)
    if any(word in lowered for word in CONFIRM_WORDS):
        return BridgeIntent("confirm", raw=text)
    if any(word in lowered for word in CANCEL_WORDS):
        return BridgeIntent("cancel", raw=text)
    if any(word in lowered for word in REPEAT_WORDS):
        return BridgeIntent("repeat", raw=text)
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
    if any(word in lowered for word in RESUME_CODEX_WORDS):
        return BridgeIntent("codex_resume", raw=text)
    if any(word in lowered for word in CODE_REVIEW_WORDS):
        return BridgeIntent("codex_review", raw=text)
    if any(word in lowered for word in GIT_STATUS_WORDS):
        return BridgeIntent("git_status", raw=text)
    if "codex" in lowered and not any(lowered.startswith(prefix) for prefix in CODEX_PREFIXES):
        codex_index = lowered.find("codex")
        payload = lowered[codex_index + len("codex"):].strip()
        if payload:
            return BridgeIntent("codex_exec", payload=payload, raw=text)
    fuzzy_action = fuzzy_match_action(lowered)
    if fuzzy_action is not None:
        return BridgeIntent(fuzzy_action, raw=text)
    for prefix in CODEX_PREFIXES:
        if lowered.startswith(prefix):
            payload = lowered[len(prefix):].strip()
            for nested_prefix in CODEX_PREFIXES:
                if payload.startswith(nested_prefix):
                    payload = payload[len(nested_prefix):].strip()
                    break
            return BridgeIntent("codex_exec", payload=payload, raw=text)
    if wake_word and lowered:
        return BridgeIntent("codex_exec", payload=lowered, raw=text)
    return BridgeIntent("unknown", raw=text)


def requires_confirmation(intent: BridgeIntent) -> bool:
    return intent.action in ("run_tests", "codex_exec", "codex_resume", "codex_review")


def describe_intent(intent: BridgeIntent) -> str:
    if intent.action == "run_tests":
        return "run tests"
    if intent.action == "codex_exec":
        payload = (intent.payload or "").strip()
        return f"ask Codex to {payload}" if payload else "ask Codex"
    if intent.action == "codex_resume":
        return "resume the last Codex task"
    if intent.action == "codex_review":
        return "run a code review"
    if intent.action == "pair_test":
        return "run pair test"
    if intent.action == "doctor":
        return "run doctor"
    if intent.action == "scan":
        return "scan Frame"
    if intent.action == "git_status":
        return "show git status"
    if intent.action == "list_tasks":
        return "list tasks"
    if intent.action == "pin_next_task":
        return "pin next task"
    return intent.action.replace("_", " ")


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




async def run_codex_resume(args) -> Tuple[int, str]:
    repo = Path(args.repo).expanduser().resolve()
    with tempfile.NamedTemporaryFile(prefix="voice_codex_resume_", suffix=".txt", delete=False) as handle:
        output_file = Path(handle.name)

    command = [
        args.codex_bin,
        "exec",
        "resume",
        "--last",
        "--cd",
        str(repo),
        "--output-last-message",
        str(output_file),
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
    return code, final_text or output or "Codex resume returned no message"


async def run_codex_review(args) -> Tuple[int, str]:
    repo = Path(args.repo).expanduser().resolve()
    with tempfile.NamedTemporaryFile(prefix="voice_codex_review_", suffix=".txt", delete=False) as handle:
        output_file = Path(handle.name)

    command = [
        args.codex_bin,
        "exec",
        "review",
        "--uncommitted",
        "--cd",
        str(repo),
        "--output-last-message",
        str(output_file),
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
    return code, final_text or output or "Codex review returned no message"

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
    locale = locale_for_args(args)
    if intent.action == "help":
        return help_message(locale), False
    if intent.action == "exit":
        return stop_message(locale), True
    if intent.action == "ignored":
        return "", False
    if intent.action == "unknown":
        return unknown_message(locale), False
    if intent.action == "confirm":
        return nothing_pending(locale, "confirm"), False
    if intent.action == "cancel":
        return nothing_pending(locale, "cancel"), False

    if intent.action == "doctor":
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "doctor"], repo, args.dry_run)
        return args.compact_text(summarize_doctor_output(output or f"doctor exit {code}", locale=locale)), False
    if intent.action == "scan":
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "scan"], repo, args.dry_run)
        return args.compact_text(summarize_scan_output(output or f"scan exit {code}", locale=locale)), False
    if intent.action == "pair_test":
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "pair-test", "--", "--text", "Hello from voice bridge"], repo, args.dry_run)
        return args.compact_text(summarize_pair_test_output(output or f"pair-test exit {code}", locale=locale)), False
    if intent.action == "list_tasks":
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "task-board", "--", "list"], repo, args.dry_run)
        return args.compact_text(summarize_task_list_output(output or f"task list exit {code}", locale=locale)), False
    if intent.action == "pin_next_task":
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "task-board", "--", "pin-next"], repo, args.dry_run)
        return args.compact_text(output or f"pin-next exit {code}"), False
    if intent.action == "git_status":
        code, output = await run_shell_text("git status --short --branch", repo, args.dry_run)
        return args.compact_text(summarize_git_status(output or f"git status exit {code}", locale=locale)), False
    if intent.action == "run_tests":
        code, output = await run_shell_text(args.test_command, repo, args.dry_run)
        label = "tests passed" if code == 0 else f"tests failed ({code})"
        detail = args.compact_text(summarize_pytest_output(output or label, code, locale=locale))
        return detail, False
    if intent.action == "codex_resume":
        code, output = await run_codex_resume(args)
        label = summarize_codex_output(output or f"codex resume exit {code}", locale=locale)
        return args.compact_text(f"CODEX {label}"), False
    if intent.action == "codex_review":
        code, output = await run_codex_review(args)
        label = summarize_codex_output(output or f"codex review exit {code}", locale=locale)
        return args.compact_text(f"CODEX {label}"), False
    if intent.action == "codex_exec":
        code, output = await run_codex_exec(args, intent.payload or "")
        label = summarize_codex_output(output or f"codex exit {code}", locale=locale)
        return args.compact_text(f"CODEX {label}"), False

    return "VOICE CODEX unsupported action.", False
