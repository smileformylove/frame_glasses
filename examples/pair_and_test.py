import argparse
import asyncio
from typing import Optional

from bleak import BleakScanner
from frame_ble import FrameBle

from frame_utils import connect_with_retry, initialize_frame, lua_escape


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan for the nearest Frame and send a test message")
    parser.add_argument("--timeout", type=float, default=8.0, help="BLE scan timeout in seconds")
    parser.add_argument("--name-contains", default=None, help="Optional substring filter for Frame device names")
    parser.add_argument("--text", default="Hello from Mac mini", help="Text displayed on Frame after connection")
    parser.add_argument("--x", type=int, default=1, help="Display x coordinate")
    parser.add_argument("--y", type=int, default=1, help="Display y coordinate")
    parser.add_argument("--dry-run", action="store_true", help="Print which device would be used without connecting")
    parser.add_argument("--verbose", action="store_true", help="Print BLE scan and connect progress")
    return parser


async def find_best_frame(timeout: float, name_contains: Optional[str], verbose: bool = False) -> Optional[dict]:
    service_uuid = FrameBle._SERVICE_UUID
    if verbose:
        print(f"[pair-test] scanning for Frame devices for {timeout:.1f}s ...")
    discovered = await BleakScanner.discover(timeout=timeout, return_adv=True, service_uuids=[service_uuid])
    needle = name_contains.lower() if name_contains else None
    matches = []

    for _, item in discovered.items():
        device, adv = item
        local_name = adv.local_name or device.name or "<unknown>"
        if needle and needle not in local_name.lower():
            continue
        if service_uuid not in list(adv.service_uuids or []):
            continue
        matches.append(
            {
                "name": local_name,
                "address": device.address,
                "rssi": adv.rssi,
            }
        )

    if not matches:
        return None

    matches.sort(key=lambda row: row["rssi"], reverse=True)
    return matches[0]


async def send_text(name: str, text: str, x: int, y: int, verbose: bool = False) -> None:
    frame = FrameBle()
    if verbose:
        print(f"[pair-test] connecting to {name} ...")
    address = await connect_with_retry(frame, name=name, verbose=verbose)
    if verbose:
        print(f"[pair-test] connected to {address}")
    try:
        if verbose:
            print("[pair-test] sending break/reset/break ...")
        await frame.send_break_signal()
        await frame.send_reset_signal()
        if verbose:
            print("[pair-test] sending break/reset/break ...")
        await frame.send_break_signal()
        command = f"frame.display.text('{lua_escape(text)}',{x},{y});frame.display.show();print(0)"
        await frame.send_lua(command, await_print=True)
        if verbose:
            print("[pair-test] text sent successfully")
    finally:
        if frame.is_connected():
            await frame.disconnect()


async def async_main() -> None:
    args = build_parser().parse_args()
    match = await find_best_frame(args.timeout, args.name_contains, args.verbose)
    if not match:
        print("No matching Frame found.")
        print("Tips:")
        print("- Wake the glasses and keep them near the Mac")
        print("- If they were paired elsewhere, forget them and re-enter pairing mode")
        print("- Disconnect phone apps or other computers")
        return

    print(f"Selected Frame: {match['name']} ({match['address']}, RSSI {match['rssi']})")
    if args.dry_run:
        print(f"Would display: {args.text}")
        return

    await send_text(match["name"], args.text, args.x, args.y, args.verbose)
    print("Test message sent successfully.")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
