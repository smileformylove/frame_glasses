import argparse
import asyncio
from pathlib import Path

from frame_utils import FrameUnicodeDisplay, cardify_text
from voice_history import summarize_history
from voice_task_state import get_current_task, summarize_recent_tasks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Show a deterministic multi-card demo on the glasses screen')
    parser.add_argument('--name', default=None, help='Optional BLE device name such as "Frame EF"')
    parser.add_argument('--render-mode', choices=('plain', 'unicode'), default='unicode')
    parser.add_argument('--font-family', default=None)
    parser.add_argument('--font-size', type=int, default=40)
    parser.add_argument('--display-width', type=int, default=520)
    parser.add_argument('--max-rows', type=int, default=2)
    parser.add_argument('--delay', type=float, default=1.8, help='Seconds between cards')
    parser.add_argument('--task-state-file', default='./profiles/voice_task_state.json')
    parser.add_argument('--history-file', default='./profiles/voice_history.json')
    parser.add_argument('--dry-run', action='store_true')
    return parser


async def main_async() -> None:
    args = build_parser().parse_args()
    display = FrameUnicodeDisplay(
        name=args.name,
        dry_run=args.dry_run,
        font_family=args.font_family,
        font_size=args.font_size,
        display_width=args.display_width,
        max_rows=args.max_rows,
    )
    current_task = get_current_task(Path(args.task_state_file).expanduser())
    recent_tasks = summarize_recent_tasks(Path(args.task_state_file).expanduser(), locale='zh')
    history = summarize_history(Path(args.history_file).expanduser(), locale='zh')
    cards = []
    if current_task:
        cards.extend(cardify_text(f"当前任务：{current_task.get('title','')}", max_chars=40, include_index=False))
    cards.extend(cardify_text(f"最近任务：{recent_tasks}", max_chars=40, include_index=False))
    cards.extend(cardify_text(f"最近命令：{history}", max_chars=40, include_index=False))
    await display.connect()
    try:
        for card in cards:
            await display.show_text(card, x=1, y=1)
            await asyncio.sleep(args.delay)
    finally:
        await display.disconnect()


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print('\nScreen demo stopped.')


if __name__ == '__main__':
    main()
