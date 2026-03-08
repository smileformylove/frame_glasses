import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_HISTORY_PATH = Path('./profiles/voice_history.json')
MAX_ENTRIES = 50


def load_history(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding='utf-8'))


def save_history(path: Path, entries: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')


def append_history(path: Path, entry: Dict[str, Any]) -> None:
    entries = load_history(path)
    entries.append({
        **entry,
        'timestamp': datetime.now().isoformat(timespec='seconds'),
    })
    save_history(path, entries[-MAX_ENTRIES:])


def summarize_history(path: Path, locale: str = 'en', limit: int = 3) -> str:
    entries = load_history(path)
    if not entries:
        return 'No history yet.' if locale == 'en' else '还没有历史记录。'
    recent = entries[-limit:]
    parts = []
    for item in reversed(recent):
        action = item.get('action', 'unknown')
        result = item.get('result', '')
        heard = item.get('heard', '')
        if locale == 'en':
            parts.append(f"{action}: {result or heard}")
        else:
            parts.append(f"{action}：{result or heard}")
    separator = ' | ' if locale == 'en' else ' ｜ '
    return separator.join(parts)


def filter_entries(entries, mode: str):
    if mode == 'errors':
        return [item for item in entries if any(token in str(item.get('result', '')) for token in ('ERROR', 'FAIL', '失败', '错误', 'warning', 'WARN', '警告'))]
    if mode == 'tasks':
        return [item for item in entries if str(item.get('action', '')).startswith('task_')]
    if mode == 'codex':
        return [item for item in entries if str(item.get('action', '')).startswith('codex_') or 'CODEX' in str(item.get('result', ''))]
    return entries


def summarize_history_filtered(path: Path, mode: str, locale: str = 'en', limit: int = 3) -> str:
    entries = filter_entries(load_history(path), mode)
    if not entries:
        if locale == 'zh':
            mapping = {'errors': '最近没有错误记录。', 'tasks': '最近没有任务记录。', 'codex': '最近没有 Codex 记录。'}
            return mapping.get(mode, '还没有历史记录。')
        mapping = {'errors': 'No recent errors.', 'tasks': 'No recent task history.', 'codex': 'No recent Codex history.'}
        return mapping.get(mode, 'No history yet.')
    recent = entries[-limit:]
    parts = []
    for item in reversed(recent):
        action = item.get('action', 'unknown')
        result = item.get('result', '')
        heard = item.get('heard', '')
        if locale == 'en':
            parts.append(f"{action}: {result or heard}")
        else:
            parts.append(f"{action}：{result or heard}")
    separator = ' | ' if locale == 'en' else ' ｜ '
    return separator.join(parts)
