import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONTEXT_PATH = Path('./profiles/voice_context.json')


def load_contexts(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def save_contexts(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def load_last_message(path: Path, key: str) -> Optional[str]:
    contexts = load_contexts(path)
    item = contexts.get(key)
    if not item:
        return None
    return item.get('last_message')


def save_last_message(path: Path, key: str, message: str) -> None:
    contexts = load_contexts(path)
    contexts[key] = {
        'last_message': message,
        'updated_at': datetime.now().isoformat(timespec='seconds'),
    }
    save_contexts(path, contexts)
