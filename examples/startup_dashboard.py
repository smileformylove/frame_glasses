from pathlib import Path
from typing import List, Tuple

from voice_history import summarize_history
from voice_task_state import get_current_task, summarize_recent_tasks


def _is_empty_summary(summary: str, locale: str) -> bool:
    if locale == "zh":
        return summary in ("", "还没有最近任务。", "还没有历史记录。")
    return summary in ("", "No recent tasks.", "No history yet.")


def build_startup_messages(args, settings: str = "", locale: str = "zh") -> Tuple[List[str], int]:
    if locale == "en":
        ready = "VOICE CODEX ready. Say codex plus a command."
        empty_task = "No current task yet. Say start task ..."
        recent_tasks_label = "Recent tasks"
        recent_history_label = "Recent commands"
        current_task_label = "Current task"
    else:
        ready = "VOICE CODEX 已就绪。说：codex 加指令。"
        empty_task = "当前无任务。可说：开始任务 ..."
        recent_tasks_label = "最近任务"
        recent_history_label = "最近命令"
        current_task_label = "当前任务"

    if settings and not getattr(args, "visual_broadcast", False):
        ready = f"{ready}\n{settings}"

    items: List[str] = [ready]
    preferred_index = 0

    task = get_current_task(Path(args.task_state_file).expanduser())
    if task and task.get("title"):
        items.append(f"{current_task_label}：{task.get('title', '')}")
        preferred_index = len(items) - 1
    else:
        items.append(empty_task)
        preferred_index = len(items) - 1

    recent_tasks = summarize_recent_tasks(Path(args.task_state_file).expanduser(), locale=locale, limit=2)
    if not _is_empty_summary(recent_tasks, locale):
        items.append(f"{recent_tasks_label}：{recent_tasks}")

    if not getattr(args, "visual_broadcast", False):
        recent_history = summarize_history(Path(args.history_file).expanduser(), locale=locale, limit=2)
        if not _is_empty_summary(recent_history, locale):
            items.append(f"{recent_history_label}：{recent_history}")

    return items, preferred_index
