import difflib
import re
import asyncio
import subprocess
import sys
import shutil
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
from voice_history import DEFAULT_HISTORY_PATH, summarize_history
from voice_task_state import DEFAULT_TASK_STATE_PATH, clear_current_task, get_current_task, set_current_task
from weather_time import current_time_text, fetch_weather


DEFAULT_COMMANDS = "help|time|weather|doctor|scan frame|pair test|git status|list tasks|pin next task|run tests|start task summarize repo|current task|continue task|clear task|resume codex|code review|ask codex summarize the repo|repeat|history|why failed|details|confirm|cancel|exit"
DEFAULT_HELP_TEXT = "VOICE CODEX help: time, weather, doctor, scan, pair test, git status, list tasks, pin next task, run tests, start task ..., current task, continue task, clear task, resume codex, code review, ask codex ..., repeat, why failed, details, confirm, cancel, exit"
EXIT_WORDS = ("exit", "quit", "stop", "结束", "退出", "停止")
FILLER_PREFIXES = ("please ", "can you ", "could you ", "请", "帮我", "麻烦", "现在", "能不能")
HELP_WORDS = ("help", "what can you do", "commands", "帮助")
TIME_WORDS = ("time", "what time is it", "现在几点", "几点了", "几点", "几点钟", "时间")
WEATHER_WORDS = ("weather", "天气", "上海天气", "天气怎么样")
CONFIRM_WORDS = ("confirm", "yes", "go ahead", "do it", "确认", "执行", "继续执行", "好的")
CANCEL_WORDS = ("cancel", "no", "never mind", "stop that", "取消", "不用了", "算了")
REPEAT_WORDS = ("repeat", "say again", "again", "再说一次", "重复一下", "再来一遍")
FOLLOW_UP_WORDS = ("why failed", "why did it fail", "details", "explain more", "what happened", "为什么失败", "详细一点", "详细说明", "解释一下")
HISTORY_WORDS = ("history", "recent commands", "show history", "最近命令", "最近结果", "历史记录")
DOCTOR_WORDS = ("doctor", "check environment", "环境检查", "检查环境")
SCAN_WORDS = ("scan frame", "scan device", "扫描眼镜", "扫描设备")
PAIR_TEST_WORDS = ("pair test", "test connection", "连接测试", "配对测试")
GIT_STATUS_WORDS = ("git status", "status", "git 状态", "代码状态", "仓库状态")
LIST_TASKS_WORDS = ("list tasks", "show tasks", "任务列表", "列任务", "查看任务", "看看任务")
PIN_NEXT_TASK_WORDS = ("pin next task", "focus task", "pin task", "置顶任务", "下一任务", "聚焦任务", "置顶下一任务")
RUN_TESTS_WORDS = ("run tests", "run test", "运行测试", "测试一下", "跑测试", "执行测试", "开始测试", "做测试")
TASK_START_WORDS = ("start task", "new task", "开始任务", "新任务", "创建任务")
CURRENT_TASK_WORDS = ("current task", "task status", "当前任务", "现在任务")
CONTINUE_TASK_WORDS = ("continue task", "继续任务", "继续当前任务")
CLEAR_TASK_WORDS = ("clear task", "清除任务", "结束任务")
RESUME_CODEX_WORDS = ("resume codex", "resume last codex", "continue codex", "继续 codex", "继续上次 codex", "继续上次任务")
CODE_REVIEW_WORDS = ("code review", "review code", "review repo", "代码审查", "代码 review", "审查代码", "检查代码")
CODEX_PREFIXES = ("ask codex ", "codex ", "让 codex ", "请 codex ", "让 codex 帮我", "请 codex 帮我")


WAKE_WORD_ALIASES = {
    'codex': ('codex', 'code x', 'codx', 'codec', '靠双手', '靠雙手', '考德斯', '考克斯', '科德克斯', '口袋克斯'),
}


def wake_word_candidates(wake_word: str):
    normalized = normalize_command_text(wake_word)
    aliases = WAKE_WORD_ALIASES.get(normalized, ())
    return tuple(dict.fromkeys([normalized, *aliases]))



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
    "time": ("time", "what time is it", "现在几点", "时间"),
    "weather": ("weather", "天气", "天气怎么样"),
    "doctor": ("doctor", "check environment", "环境检查", "检查环境"),
    "scan": ("scan frame", "scan device", "扫描眼镜", "扫描设备", "扫描 frame"),
    "pair_test": ("pair test", "test connection", "连接测试", "配对测试", "测试连接"),
    "git_status": ("git status", "git 状态", "代码状态", "仓库状态"),
    "list_tasks": ("list tasks", "show tasks", "任务列表", "列任务", "查看任务"),
    "pin_next_task": ("pin next task", "focus task", "置顶任务", "下一任务", "聚焦任务"),
    "run_tests": ("run tests", "运行测试", "跑测试", "执行测试"),
    "task_start": ("start task", "开始任务", "新任务"),
    "task_status": ("current task", "当前任务"),
    "task_continue": ("continue task", "继续任务"),
    "task_clear": ("clear task", "清除任务", "结束任务"),
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

    for candidate in wake_word_candidates(wake_word):
        alias = normalize_command_text(candidate)
        if normalized == alias:
            return ""
        if normalized.startswith(alias + " "):
            return normalized[len(alias):].strip()
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
    if any(word in lowered for word in TIME_WORDS):
        return BridgeIntent("time", raw=text)
    if any(word in lowered for word in WEATHER_WORDS):
        payload = None
        if lowered.endswith("天气") and len(lowered) > 2:
            payload = lowered[:-2].strip() or None
        elif "weather in " in lowered:
            payload = lowered.split("weather in ", 1)[1].strip() or None
        return BridgeIntent("weather", payload=payload, raw=text)
    if any(word in lowered for word in CONFIRM_WORDS):
        return BridgeIntent("confirm", raw=text)
    if any(word in lowered for word in CANCEL_WORDS):
        return BridgeIntent("cancel", raw=text)
    if any(word in lowered for word in REPEAT_WORDS):
        return BridgeIntent("repeat", raw=text)
    if any(word in lowered for word in HISTORY_WORDS):
        return BridgeIntent("history", raw=text)
    if any(word in lowered for word in FOLLOW_UP_WORDS):
        return BridgeIntent("follow_up", raw=text)
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
    if any(word in lowered for word in CURRENT_TASK_WORDS):
        return BridgeIntent("task_status", raw=text)
    if any(word in lowered for word in CONTINUE_TASK_WORDS):
        return BridgeIntent("task_continue", raw=text)
    if any(word in lowered for word in CLEAR_TASK_WORDS):
        return BridgeIntent("task_clear", raw=text)
    for prefix in TASK_START_WORDS:
        if lowered.startswith(prefix):
            payload = lowered[len(prefix):].strip()
            return BridgeIntent("task_start", payload=payload, raw=text)
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


def describe_intent(intent: BridgeIntent, locale: str = 'en') -> str:
    if locale == 'zh':
        if intent.action == "run_tests":
            return "运行测试"
        if intent.action == "codex_exec":
            payload = (intent.payload or "").strip()
            return f"让 Codex：{payload}" if payload else "让 Codex 执行"
        if intent.action == "codex_resume":
            return "继续最近一次 Codex 会话"
        if intent.action == "codex_review":
            return "执行代码审查"
        if intent.action == "pair_test":
            return "执行连接测试"
        if intent.action == "time":
            return "查看当前时间"
        if intent.action == "weather":
            return "查看天气"
        if intent.action == "doctor":
            return "执行环境检查"
        if intent.action == "scan":
            return "扫描 Frame 设备"
        if intent.action == "git_status":
            return "查看 git 状态"
        if intent.action == "list_tasks":
            return "读取任务列表"
        if intent.action == "pin_next_task":
            return "置顶下一任务"
        if intent.action == "task_start":
            payload = (intent.payload or "").strip()
            return f"开始任务：{payload}" if payload else "开始任务"
        if intent.action == "task_status":
            return "查看当前任务"
        if intent.action == "task_continue":
            return "继续当前任务"
        if intent.action == "task_clear":
            return "清除当前任务"
        return intent.action.replace("_", " ")

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
    if intent.action == "time":
        return "show current time"
    if intent.action == "weather":
        return "show weather"
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
    if intent.action == "task_start":
        payload = (intent.payload or "").strip()
        return f"start task: {payload}" if payload else "start task"
    if intent.action == "task_status":
        return "show current task"
    if intent.action == "task_continue":
        return "continue current task"
    if intent.action == "task_clear":
        return "clear current task"
    if intent.action == "task_start":
        return "start task"
    if intent.action == "task_status":
        return "current task"
    if intent.action == "task_continue":
        return "continue task"
    if intent.action == "task_clear":
        return "clear task"
    return intent.action.replace("_", " ")


def confirmation_prompt(intent: "BridgeIntent", locale: str = 'en') -> str:
    if locale == 'en':
        return f"Confirm {describe_intent(intent, locale)}? Say confirm or cancel."
    return f"确认执行：{describe_intent(intent, locale)}。请说 confirm 或 cancel。"


def progress_message(intent: BridgeIntent, locale: str = 'en') -> str:
    if locale == 'zh':
        if intent.action == 'run_tests':
            return '正在运行测试...'
        if intent.action == 'codex_resume':
            return '正在继续最近一次 Codex 会话...'
        if intent.action == 'codex_review':
            return '正在执行代码审查...'
        if intent.action == 'codex_exec':
            return '正在请求 Codex...'
        return '正在执行...'
    if intent.action == 'run_tests':
        return 'Running tests...'
    if intent.action == 'codex_resume':
        return 'Resuming the last Codex task...'
    if intent.action == 'codex_review':
        return 'Running code review...'
    if intent.action == 'codex_exec':
        return 'Asking Codex...'
    return 'Running command...'


def build_follow_up_prompt(last_message: str, locale: str = 'en') -> str:
    if locale == 'zh':
        return f"请根据这条上一结果做简短解释，并优先说明失败原因或下一步建议：{last_message}"
    return f"Briefly explain this previous result and focus on the likely failure reason or next step: {last_message}"


def dry_run_message(intent: BridgeIntent, args, locale: str) -> str:
    if intent.action == 'time':
        return 'Would show current time' if locale == 'en' else '将查看当前时间'
    if intent.action == 'weather':
        location = (intent.payload or getattr(args, 'default_weather_location', 'Shanghai'))
        return f'Would fetch weather for {location}' if locale == 'en' else f'将查询天气：{location}'
    if intent.action == 'doctor':
        return 'Would run doctor' if locale == 'en' else '将执行环境检查'
    if intent.action == 'scan':
        return 'Would scan Frame devices' if locale == 'en' else '将扫描 Frame 设备'
    if intent.action == 'pair_test':
        return 'Would run pair test' if locale == 'en' else '将执行连接测试'
    if intent.action == 'list_tasks':
        return 'Would list tasks' if locale == 'en' else '将读取任务列表'
    if intent.action == 'pin_next_task':
        return 'Would pin next task' if locale == 'en' else '将置顶下一任务'
    if intent.action == 'git_status':
        return 'Would check git status' if locale == 'en' else '将查看 git 状态'
    if intent.action == 'run_tests':
        return f"Would run tests: {args.test_command}" if locale == 'en' else f"将运行测试：{args.test_command}"
    if intent.action == 'task_start':
        payload = (intent.payload or '').strip()
        return f"Would start task: {payload}" if locale == 'en' else f"将开始任务：{payload}"
    if intent.action == 'task_status':
        return 'Would show current task' if locale == 'en' else '将查看当前任务'
    if intent.action == 'task_continue':
        return 'Would continue current task' if locale == 'en' else '将继续当前任务'
    if intent.action == 'task_clear':
        return 'Would clear current task' if locale == 'en' else '将清除当前任务'
    if intent.action == 'codex_resume':
        return 'Would resume the last Codex task' if locale == 'en' else '将继续最近一次 Codex 会话'
    if intent.action == 'codex_review':
        return 'Would run a code review' if locale == 'en' else '将执行代码审查'
    if intent.action == 'codex_exec':
        payload = (intent.payload or '').strip()
        return f"Would ask Codex to {payload}" if locale == 'en' else f"将让 Codex：{payload}"
    return 'Would run action' if locale == 'en' else '将执行动作'


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




def resolve_codex_bin(args) -> str:
    candidates = []
    configured = getattr(args, 'codex_bin', None)
    if configured:
        candidates.append(configured)
    candidates.extend([
        'codex',
        '/Applications/Codex.app/Contents/Resources/codex',
        str(Path.home() / 'Applications/Codex.app/Contents/Resources/codex'),
    ])

    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) if '/' not in candidate else candidate
        if resolved and Path(resolved).exists():
            return str(Path(resolved))

    raise RuntimeError('Codex CLI not found. Set --codex-bin explicitly or install Codex.app.')


async def run_codex_resume(args) -> Tuple[int, str]:
    repo = Path(args.repo).expanduser().resolve()
    with tempfile.NamedTemporaryFile(prefix="voice_codex_resume_", suffix=".txt", delete=False) as handle:
        output_file = Path(handle.name)

    codex_bin = resolve_codex_bin(args)
    command = [
        codex_bin,
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

    codex_bin = resolve_codex_bin(args)
    command = [
        codex_bin,
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

    codex_bin = resolve_codex_bin(args)
    command = [
        codex_bin,
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
    if intent.action == "history":
        return summarize_history(Path(args.history_file).expanduser(), locale=locale), False

    if intent.action == "time":
        return args.compact_text(current_time_text(locale=locale, timezone_name=getattr(args, "time_zone", None))), False
    if intent.action == "weather":
        if args.dry_run:
            return dry_run_message(intent, args, locale), False
        location = intent.payload or getattr(args, "default_weather_location", "Shanghai")
        return args.compact_text(fetch_weather(location, locale=locale)), False

    if intent.action == "doctor":
        if args.dry_run:
            return dry_run_message(intent, args, locale), False
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "doctor"], repo, args.dry_run)
        return args.compact_text(summarize_doctor_output(output or f"doctor exit {code}", locale=locale)), False
    if intent.action == "scan":
        if args.dry_run:
            return dry_run_message(intent, args, locale), False
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "scan"], repo, args.dry_run)
        return args.compact_text(summarize_scan_output(output or f"scan exit {code}", locale=locale)), False
    if intent.action == "pair_test":
        if args.dry_run:
            return dry_run_message(intent, args, locale), False
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "pair-test", "--", "--text", "Hello from voice bridge"], repo, args.dry_run)
        return args.compact_text(summarize_pair_test_output(output or f"pair-test exit {code}", locale=locale)), False
    if intent.action == "list_tasks":
        if args.dry_run:
            return dry_run_message(intent, args, locale), False
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "task-board", "--", "list"], repo, args.dry_run)
        return args.compact_text(summarize_task_list_output(output or f"task list exit {code}", locale=locale)), False
    if intent.action == "pin_next_task":
        if args.dry_run:
            return dry_run_message(intent, args, locale), False
        code, output = await run_subprocess([sys.executable, str(repo / "frame_lab.py"), "task-board", "--", "pin-next"], repo, args.dry_run)
        return args.compact_text(output or f"pin-next exit {code}"), False
    if intent.action == "git_status":
        if args.dry_run:
            return dry_run_message(intent, args, locale), False
        code, output = await run_shell_text("git status --short --branch", repo, args.dry_run)
        return args.compact_text(summarize_git_status(output or f"git status exit {code}", locale=locale)), False
    if intent.action == "run_tests":
        if args.dry_run:
            return dry_run_message(intent, args, locale), False
        code, output = await run_shell_text(args.test_command, repo, args.dry_run)
        label = "tests passed" if code == 0 else f"tests failed ({code})"
        detail = args.compact_text(summarize_pytest_output(output or label, code, locale=locale))
        return detail, False
    if intent.action == "task_start":
        task_payload = (intent.payload or "").strip()
        if not task_payload:
            return ("Task description missing." if locale == "en" else "缺少任务描述。"), False
        set_current_task(Path(args.task_state_file).expanduser(), task_payload, task_payload)
        if args.dry_run:
            return dry_run_message(intent, args, locale), False
        code, output = await run_codex_exec(args, task_payload)
        label = summarize_codex_output(output or f"codex exit {code}", locale=locale)
        return args.compact_text(f"CODEX {label}"), False
    if intent.action == "task_status":
        task = get_current_task(Path(args.task_state_file).expanduser())
        if not task:
            return ("No current task." if locale == "en" else "当前没有任务。"), False
        title = task.get("title", "")
        return (f"Current task: {title}" if locale == "en" else f"当前任务：{title}"), False
    if intent.action == "task_continue":
        task = get_current_task(Path(args.task_state_file).expanduser())
        if not task:
            return ("No current task to continue." if locale == "en" else "当前没有可继续的任务。"), False
        payload = task.get("payload") or task.get("title", "")
        if args.dry_run:
            return dry_run_message(intent, args, locale), False
        code, output = await run_codex_resume(args)
        label = summarize_codex_output(output or f"codex resume exit {code}", locale=locale)
        return args.compact_text(f"CODEX {label}"), False
    if intent.action == "task_clear":
        clear_current_task(Path(args.task_state_file).expanduser())
        return ("Current task cleared." if locale == "en" else "当前任务已清除。"), False
    if intent.action == "codex_resume":
        if args.dry_run:
            return dry_run_message(intent, args, locale), False
        code, output = await run_codex_resume(args)
        label = summarize_codex_output(output or f"codex resume exit {code}", locale=locale)
        return args.compact_text(f"CODEX {label}"), False
    if intent.action == "codex_review":
        if args.dry_run:
            return dry_run_message(intent, args, locale), False
        code, output = await run_codex_review(args)
        label = summarize_codex_output(output or f"codex review exit {code}", locale=locale)
        return args.compact_text(f"CODEX {label}"), False
    if intent.action == "codex_exec":
        if args.dry_run:
            return dry_run_message(intent, args, locale), False
        code, output = await run_codex_exec(args, intent.payload or "")
        label = summarize_codex_output(output or f"codex exit {code}", locale=locale)
        return args.compact_text(f"CODEX {label}"), False

    return "VOICE CODEX unsupported action.", False
