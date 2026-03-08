import argparse
import asyncio
import json
import platform
import subprocess
import sys
import traceback
from typing import Optional

from bleak import BleakScanner
from frame_ble import FrameBle

from frame_utils import lua_escape


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe the real Frame connectivity path step by step")
    parser.add_argument("--name", default=None, help="Optional Frame BLE name such as 'Frame EF'")
    parser.add_argument("--timeout", type=float, default=6.0, help="BLE scan timeout in seconds")
    parser.add_argument("--send-text", default=None, help="Optional text to display after connect succeeds")
    parser.add_argument("--show-all", action="store_true", help="Show all BLE devices instead of only Frame service matches")
    return parser


async def run_probe(args) -> int:
    print(f"[probe] python_executable={sys.executable}")
    print(f"[probe] python_version={sys.version.split()[0]}")
    print(f"[probe] platform={platform.platform()}")

    if platform.system() == "Darwin":
        print("[probe] system_profiler bluetooth snippet:")
        snippet = subprocess.run(
            ["/usr/sbin/system_profiler", "SPBluetoothDataType"],
            capture_output=True,
            text=True,
        ).stdout
        for line in snippet.splitlines():
            if "Frame" in line or "Bluetooth:" in line or "Connected:" in line or "Not Connected:" in line:
                print(f"  {line}")

    service_uuid = FrameBle._SERVICE_UUID
    kwargs = {} if args.show_all else {"service_uuids": [service_uuid]}
    print(f"[probe] scanning for {args.timeout:.1f}s ...")
    discovered = await BleakScanner.discover(timeout=args.timeout, return_adv=True, **kwargs)
    print(f"[probe] discovered_count={len(discovered)}")
    matches = []
    for _, item in discovered.items():
        device, adv = item
        local_name = adv.local_name or device.name or "<unknown>"
        services = list(adv.service_uuids or [])
        row = {
            "name": local_name,
            "address": device.address,
            "rssi": adv.rssi,
            "services": services,
        }
        if args.show_all or service_uuid in services:
            matches.append(row)
            print(f"[probe] candidate name={local_name} address={device.address} rssi={adv.rssi} services={services}")

    frame_name = args.name
    if not frame_name:
        for match in matches:
            if match["name"].startswith("Frame"):
                frame_name = match["name"]
                break

    if not frame_name:
        print("[probe] no Frame candidate selected")
        return 2

    print(f"[probe] selected_name={frame_name}")
    frame = FrameBle()
    try:
        print(f"[probe] connecting to {frame_name} ...")
        address = await frame.connect(name=frame_name)
        print(f"[probe] connected address={address}")
        print(f"[probe] max_lua_payload={frame.max_lua_payload()} max_data_payload={frame.max_data_payload()}")

        print("[probe] sending break/reset/break ...")
        await frame.send_break_signal()
        await frame.send_reset_signal()
        await frame.send_break_signal()
        print("[probe] frame ready")

        if args.send_text:
            command = f"frame.display.text('{lua_escape(args.send_text)}',1,1);frame.display.show();print(0)"
            print(f"[probe] sending text={args.send_text!r}")
            result = await frame.send_lua(command, await_print=True)
            print(f"[probe] send_lua result={result!r}")

        return 0
    except BaseException as exc:
        print(f"[probe] exception={exc!r}")
        traceback.print_exc()
        return 1
    finally:
        try:
            if frame.is_connected():
                print("[probe] disconnecting ...")
                await frame.disconnect()
                print("[probe] disconnected")
        except Exception as exc:
            print(f"[probe] disconnect exception={exc!r}")


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(run_probe(args)))


if __name__ == "__main__":
    main()
