import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_TASK_STATE_PATH = Path('./profiles/voice_task_state.json')


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def save_state(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def get_current_task(path: Path) -> Optional[Dict[str, Any]]:
    return load_state(path).get('current_task')


def set_current_task(path: Path, title: str, payload: str) -> None:
    state = load_state(path)
    state['current_task'] = {
        'title': title,
        'payload': payload,
        'updated_at': datetime.now().isoformat(timespec='seconds'),
    }
    save_state(path, state)


def clear_current_task(path: Path) -> None:
    state = load_state(path)
    state.pop('current_task', None)
    save_state(path, state)
