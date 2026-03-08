import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_TASK_STATE_PATH = Path('./profiles/voice_task_state.json')
MAX_RECENT_TASKS = 10


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def save_state(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def get_current_task(path: Path) -> Optional[Dict[str, Any]]:
    return load_state(path).get('current_task')


def get_recent_tasks(path: Path) -> List[Dict[str, Any]]:
    return load_state(path).get('recent_tasks', [])


def set_current_task(path: Path, title: str, payload: str) -> None:
    state = load_state(path)
    task = {
        'title': title,
        'payload': payload,
        'updated_at': datetime.now().isoformat(timespec='seconds'),
    }
    state['current_task'] = task

    recent = state.get('recent_tasks', [])
    recent = [item for item in recent if item.get('title') != title]
    recent.append(task)
    state['recent_tasks'] = recent[-MAX_RECENT_TASKS:]
    save_state(path, state)


def clear_current_task(path: Path) -> None:
    state = load_state(path)
    state.pop('current_task', None)
    save_state(path, state)


def summarize_recent_tasks(path: Path, locale: str = 'en', limit: int = 3) -> str:
    recent = get_recent_tasks(path)
    if not recent:
        return 'No recent tasks.' if locale == 'en' else '还没有最近任务。'
    items = recent[-limit:]
    if locale == 'en':
        return ' | '.join(f"task: {item.get('title','')}" for item in reversed(items))
    return ' ｜ '.join(f"任务：{item.get('title','')}" for item in reversed(items))


def switch_to_previous_task(path: Path) -> Optional[Dict[str, Any]]:
    state = load_state(path)
    recent = state.get('recent_tasks', [])
    if len(recent) < 2:
        return None
    previous = recent[-2]
    state['current_task'] = previous
    save_state(path, state)
    return previous
