import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_CARD_STATE_PATH = Path('./profiles/voice_cards.json')


def load_card_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def save_card_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def set_cards(path: Path, key: str, cards: List[str], current_index: int = 0) -> None:
    state = load_card_state(path)
    state[key] = {
        'cards': cards,
        'current_index': max(0, min(current_index, len(cards) - 1)) if cards else 0,
    }
    save_card_state(path, state)


def update_current_index(path: Path, key: str, index: int) -> None:
    state = load_card_state(path)
    item = state.get(key)
    if not item:
        return
    cards = item.get('cards', [])
    if not cards:
        item['current_index'] = 0
    else:
        item['current_index'] = max(0, min(index, len(cards) - 1))
    state[key] = item
    save_card_state(path, state)


def get_current_card(path: Path, key: str) -> Optional[str]:
    item = load_card_state(path).get(key)
    if not item:
        return None
    cards = item.get('cards', [])
    if not cards:
        return None
    index = max(0, min(item.get('current_index', 0), len(cards) - 1))
    return cards[index]


def shift_card(path: Path, key: str, delta: int) -> Optional[str]:
    state = load_card_state(path)
    item = state.get(key)
    if not item:
        return None
    cards = item.get('cards', [])
    if not cards:
        return None
    index = item.get('current_index', 0) + delta
    index = max(0, min(index, len(cards) - 1))
    item['current_index'] = index
    state[key] = item
    save_card_state(path, state)
    return cards[index]
