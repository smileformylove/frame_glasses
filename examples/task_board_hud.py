import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from agent_hud import clear_notification, send_notification

DEFAULT_STORE = Path('./tasks/board.json')
DEFAULT_URL = 'http://127.0.0.1:8765/pin'
DEFAULT_CLEAR_URL = 'http://127.0.0.1:8765/clear'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Manage a lightweight task board and pin the current focus to Agent HUD')
    parser.add_argument('--store', default=str(DEFAULT_STORE), help='Path to the local task board JSON store')
    subparsers = parser.add_subparsers(dest='command', required=True)

    add = subparsers.add_parser('add', help='Add a new task')
    add.add_argument('--text', required=True, help='Task text')
    add.add_argument('--priority', type=int, default=3, help='Priority, lower is more important')
    add.add_argument('--tag', action='append', default=[], help='Optional tag, can be repeated')

    subparsers.add_parser('list', help='List active tasks')

    done = subparsers.add_parser('done', help='Mark a task as completed')
    done.add_argument('id', help='Task id to mark complete')

    remove = subparsers.add_parser('remove', help='Remove a task')
    remove.add_argument('id', help='Task id to remove')

    pin = subparsers.add_parser('pin-next', help='Pin the next active task to Agent HUD')
    pin.add_argument('--url', default=DEFAULT_URL, help='Agent HUD pin endpoint URL')
    pin.add_argument('--prefix', default='TASK', help='Pinned notification prefix')

    clear = subparsers.add_parser('clear-pin', help='Clear the pinned task from Agent HUD')
    clear.add_argument('--url', default=DEFAULT_CLEAR_URL, help='Agent HUD clear endpoint URL')

    return parser


def load_store(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding='utf-8'))


def save_store(path: Path, tasks: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding='utf-8')


def next_id(tasks: List[Dict[str, Any]]) -> str:
    max_num = 0
    for task in tasks:
        try:
            max_num = max(max_num, int(task['id']))
        except Exception:
            continue
    return f'{max_num + 1:04d}'


def active_tasks(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = [task for task in tasks if task.get('status') == 'open']
    return sorted(items, key=lambda task: (task.get('priority', 99), task.get('created_at', '')))


def add_task(args, store_path: Path) -> None:
    tasks = load_store(store_path)
    task = {
        'id': next_id(tasks),
        'text': args.text,
        'priority': args.priority,
        'tags': args.tag,
        'status': 'open',
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'completed_at': None,
    }
    tasks.append(task)
    save_store(store_path, tasks)
    print(f"Added task {task['id']}: {task['text']}")


def list_tasks(store_path: Path) -> None:
    tasks = active_tasks(load_store(store_path))
    if not tasks:
        print('No open tasks.')
        return
    for task in tasks:
        tags = ', '.join(task.get('tags') or [])
        suffix = f" tags=[{tags}]" if tags else ''
        print(f"{task['id']}  p{task['priority']}  {task['text']}{suffix}")


def update_status(store_path: Path, task_id: str, status: str) -> None:
    tasks = load_store(store_path)
    found = False
    for task in tasks:
        if task['id'] == task_id:
            found = True
            task['status'] = status
            task['completed_at'] = datetime.now().isoformat(timespec='seconds') if status != 'open' else None
            break
    if not found:
        print(f'Task id not found: {task_id}')
        return
    save_store(store_path, tasks)
    print(f'Updated task {task_id} -> {status}')


def remove_task(store_path: Path, task_id: str) -> None:
    tasks = load_store(store_path)
    filtered = [task for task in tasks if task['id'] != task_id]
    if len(filtered) == len(tasks):
        print(f'Task id not found: {task_id}')
        return
    save_store(store_path, filtered)
    print(f'Removed task {task_id}')


def pin_next(args, store_path: Path) -> None:
    tasks = active_tasks(load_store(store_path))
    if not tasks:
        print('No open tasks to pin.')
        return
    task = tasks[0]
    message = f"#{task['id']} p{task['priority']} {task['text']}"
    send_notification(args.url, message, args.prefix, 'info', 'task-board', sticky=True)
    print(f"Pinned task {task['id']}: {task['text']}")


def main() -> None:
    args = build_parser().parse_args()
    store_path = Path(args.store).expanduser()
    if args.command == 'add':
        add_task(args, store_path)
        return
    if args.command == 'list':
        list_tasks(store_path)
        return
    if args.command == 'done':
        update_status(store_path, args.id, 'done')
        return
    if args.command == 'remove':
        remove_task(store_path, args.id)
        return
    if args.command == 'pin-next':
        pin_next(args, store_path)
        return
    if args.command == 'clear-pin':
        clear_notification(args.url)
        print('Cleared pinned task')
        return
    raise ValueError(f'Unsupported command: {args.command}')


if __name__ == '__main__':
    main()
