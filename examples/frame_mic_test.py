import argparse
import asyncio
from pathlib import Path
from typing import Optional

from frame_msg import FrameMsg, RxAudio

from vision_hud import connect_frame_msg


DEFAULT_DURATION = 5.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record a short audio clip from the Frame microphone and save it as WAV")
    parser.add_argument("--name", help="Optional BLE device name such as 'Frame 4F'", default=None)
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION, help="Seconds to record from the Frame microphone")
    parser.add_argument("--output", default="./captures/frame_mic_test.wav", help="Path to save the WAV recording")
    parser.add_argument("--sample-rate", type=int, default=8000, help="PCM sample rate used by the Frame audio module")
    parser.add_argument("--bits-per-sample", type=int, default=16, help="PCM bit depth used by the Frame audio module")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without talking to Frame")
    return parser


async def record_from_frame(args) -> Path:
    frame = FrameMsg()
    audio = RxAudio(streaming=False)
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    queue = None

    app_source = f"""
local audio = require('audio.min')
frame.display.text('recording...',1,1)
frame.display.show()
audio.start()
local stop_at = frame.time.utc() + {args.duration}
while frame.time.utc() < stop_at do
    audio.read_and_send_audio()
    frame.sleep(0.01)
end
audio.stop()
while true do
    local chunk_len = audio.read_and_send_audio()
    if chunk_len == nil then
        break
    end
    frame.sleep(0.01)
end
print('frame_mic_done')
""".strip()

    await connect_frame_msg(frame, args.name)
    try:
        queue = await audio.attach(frame)
        await frame.upload_stdlua_libs(["audio"])
        await frame.ble.upload_file_from_string(app_source, "frame_mic_test.lua")
        await frame.start_frame_app("frame_mic_test", await_print=True)

        pcm_chunks = []
        while True:
            item = await queue.get()
            if item is None:
                break
            pcm_chunks.append(item)

        wav_bytes = RxAudio.to_wav_bytes(
            b"".join(pcm_chunks),
            sample_rate=args.sample_rate,
            bits_per_sample=args.bits_per_sample,
            channels=1,
        )
        output_path.write_bytes(wav_bytes)
        return output_path
    finally:
        if queue is not None:
            audio.detach(frame)
        try:
            await frame.stop_frame_app(reset=True)
        except Exception:
            pass
        if frame.is_connected():
            await frame.disconnect()


async def async_main() -> None:
    args = build_parser().parse_args()
    if args.dry_run:
        print(f"Would record {args.duration:.1f}s from Frame microphone to {Path(args.output).expanduser()}")
        return

    output_path = await record_from_frame(args)
    print(f"Saved Frame microphone recording to {output_path}")


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nFrame mic test stopped.")


if __name__ == "__main__":
    main()
