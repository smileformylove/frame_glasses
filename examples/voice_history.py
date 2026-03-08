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
