import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_PROFILE_PATH = Path('./profiles/frame_audio_profiles.json')


def load_profiles(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def save_profiles(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def load_profile(path: Path, frame_name: Optional[str]) -> Optional[Dict[str, Any]]:
    if not frame_name:
        return None
    profiles = load_profiles(path)
    return profiles.get(frame_name)


def save_profile(path: Path, frame_name: str, profile: Dict[str, Any]) -> None:
    profiles = load_profiles(path)
    profiles[frame_name] = {
        **profile,
        'updated_at': datetime.now().isoformat(timespec='seconds'),
    }
    save_profiles(path, profiles)
