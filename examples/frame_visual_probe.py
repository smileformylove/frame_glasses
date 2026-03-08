import argparse
import asyncio
from pathlib import Path

from frame_msg import FrameMsg

from vision_hud import connect_frame_msg


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Upload and run a persistent visual probe on Frame")
    parser.add_argument("--name", help="Optional BLE device name such as 'Frame EF'", default=None)
    parser.add_argument("--duration", type=float, default=15.0, help="Seconds to keep the visual probe running before disconnecting")
    parser.add_argument("--verbose", action="store_true", help="Print connection and upload progress")
    return parser


async def run_probe(args) -> None:
    frame = FrameMsg()
    frame_app_name = "visual_probe_frame_app"
    frame_app_path = Path(__file__).resolve().parent / "frame_apps" / f"{frame_app_name}.lua"

    if args.verbose:
        print(f"[visual-probe] connecting to {args.name or 'first available Frame'}")
    await connect_frame_msg(frame, args.name, verbose=args.verbose)
    try:
        if args.verbose:
            print(f"[visual-probe] uploading {frame_app_path.name}")
        await frame.upload_frame_app(str(frame_app_path), f"{frame_app_name}.lua")
        if args.verbose:
            print("[visual-probe] starting frame app")
        await frame.start_frame_app(frame_app_name, await_print=True)
        print(f"[visual-probe] Frame should now show a counter for {args.duration:.1f}s")
        await asyncio.sleep(args.duration)
    finally:
        try:
            await frame.stop_frame_app(reset=True)
        except Exception:
            pass
        if frame.is_connected():
            await frame.disconnect()
        if args.verbose:
            print("[visual-probe] disconnected")


def main() -> None:
    args = build_parser().parse_args()
    try:
        asyncio.run(run_probe(args))
    except KeyboardInterrupt:
        print("\nVisual probe stopped.")


if __name__ == "__main__":
    main()
