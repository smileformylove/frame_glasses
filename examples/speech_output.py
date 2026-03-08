import asyncio
import shutil
from typing import Optional


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
    command.append(text)

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.wait()
