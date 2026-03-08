import asyncio
import re
import shutil
from typing import Optional


def normalize_speak_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"\[\d+/\d+\]\s*", "", cleaned)
    cleaned = cleaned.replace('\n', '。')
    cleaned = cleaned.replace('｜', '，').replace('|', '，')
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def resolve_speech_policy(args) -> str:
    policy = getattr(args, 'speak_policy', 'off')
    if getattr(args, 'speak_results', False) and policy == 'off':
        return 'all'
    return policy


def is_high_priority_message(text: str, should_exit: bool = False) -> bool:
    important_tokens = (
        'CODEX', 'ERROR', 'FAIL', 'WARN', '测试', '失败', '错误', '警告',
        '已停止', 'stopping', '当前任务', '已切换', '已取消',
    )
    return should_exit or any(token in text for token in important_tokens)


async def speak_text(text: str, enabled: bool = False, voice: Optional[str] = None, rate: Optional[int] = None) -> None:
    if not enabled or not text:
        return
    if shutil.which('say') is None:
        return

    command = ['say']
    if voice:
        command.extend(['-v', voice])
    if rate is not None:
        command.extend(['-r', str(rate)])
    command.append(normalize_speak_text(text))

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.wait()


async def maybe_speak_result(args, text: str, should_exit: bool = False) -> None:
    policy = resolve_speech_policy(args)
    if policy == 'off':
        return
    if policy == 'important' and not is_high_priority_message(text, should_exit=should_exit):
        return
    await speak_text(text, enabled=True, voice=getattr(args, 'say_voice', None), rate=getattr(args, 'say_rate', None))
