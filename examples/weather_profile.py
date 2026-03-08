import argparse
import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_WEATHER_PROFILE_PATH = Path('./profiles/weather_profile.json')


def load_weather_profile(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def save_weather_profile(path: Path, profile: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Manage default weather preferences for voice bridges')
    parser.add_argument('--file', default=str(DEFAULT_WEATHER_PROFILE_PATH), help='Weather profile JSON path')
    subparsers = parser.add_subparsers(dest='command', required=True)

    set_cmd = subparsers.add_parser('set-default', help='Set the default weather location')
    set_cmd.add_argument('--location', required=True, help='Default city or place name')

    subparsers.add_parser('show', help='Show the current weather profile')
    return parser


def main() -> None:
    args = build_parser().parse_args()
    path = Path(args.file).expanduser()
    profile = load_weather_profile(path)
    if args.command == 'set-default':
        profile['default_weather_location'] = args.location
        save_weather_profile(path, profile)
        print(f"Default weather location set to: {args.location}")
        return
    if args.command == 'show':
        print(json.dumps(profile, ensure_ascii=False, indent=2))
        return


if __name__ == '__main__':
    main()
