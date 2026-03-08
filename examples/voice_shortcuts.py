import argparse
import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_SHORTCUTS_PATH = Path('./profiles/voice_shortcuts.json')


def load_shortcuts(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def save_shortcuts(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Manage custom voice shortcuts for Codex bridges')
    parser.add_argument('--file', default=str(DEFAULT_SHORTCUTS_PATH), help='Shortcut JSON file path')
    subparsers = parser.add_subparsers(dest='command', required=True)

    add = subparsers.add_parser('add', help='Add or update a shortcut')
    add.add_argument('--phrase', required=True, help='Trigger phrase after normalization')
    add.add_argument('--action', required=True, help='Intent action such as codex_exec, run_tests, git_status')
    add.add_argument('--payload', default=None, help='Optional payload for actions like codex_exec')

    subparsers.add_parser('list', help='List all shortcuts')

    remove = subparsers.add_parser('remove', help='Remove a shortcut')
    remove.add_argument('--phrase', required=True, help='Trigger phrase to remove')

    return parser


def normalize_phrase(phrase: str) -> str:
    return ' '.join(phrase.strip().lower().split())


def main() -> None:
    args = build_parser().parse_args()
    path = Path(args.file).expanduser()
    shortcuts = load_shortcuts(path)

    if args.command == 'add':
        key = normalize_phrase(args.phrase)
        shortcuts[key] = {'action': args.action, 'payload': args.payload}
        save_shortcuts(path, shortcuts)
        print(f'Added shortcut: {key} -> {args.action}')
        return

    if args.command == 'list':
        if not shortcuts:
            print('No shortcuts configured.')
            return
        for phrase, config in shortcuts.items():
            payload = config.get('payload')
            suffix = f" payload={payload}" if payload else ''
            print(f"{phrase} -> {config.get('action')}{suffix}")
        return

    if args.command == 'remove':
        key = normalize_phrase(args.phrase)
        if key not in shortcuts:
            print(f'Shortcut not found: {key}')
            return
        shortcuts.pop(key)
        save_shortcuts(path, shortcuts)
        print(f'Removed shortcut: {key}')
        return


if __name__ == '__main__':
    main()
