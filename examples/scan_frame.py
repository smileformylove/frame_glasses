import argparse
import asyncio
from typing import Optional

from bleak import BleakScanner
from frame_ble import FrameBle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan nearby Brilliant Labs Frame devices over BLE")
    parser.add_argument("--timeout", type=float, default=6.0, help="Scan duration in seconds")
    parser.add_argument(
        "--name-contains",
        default=None,
        help="Optional substring filter for device local names, for example Frame or 4F",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Show all BLE devices instead of only devices advertising the Frame service UUID",
    )
    return parser


async def scan(timeout: float, name_contains: Optional[str], show_all: bool) -> None:
    service_uuid = FrameBle._SERVICE_UUID
    kwargs = {} if show_all else {"service_uuids": [service_uuid]}
    discovered = await BleakScanner.discover(timeout=timeout, return_adv=True, **kwargs)

    rows = []
    needle = name_contains.lower() if name_contains else None

    for _, item in discovered.items():
        device, adv = item
        local_name = adv.local_name or device.name or "<unknown>"
        service_uuids = list(adv.service_uuids or [])
        matches_service = service_uuid in service_uuids

        if needle and needle not in local_name.lower():
            continue
        if not show_all and not matches_service:
            continue

        rows.append(
            {
                "name": local_name,
                "address": device.address,
                "rssi": adv.rssi,
                "tx_power": adv.tx_power,
                "matches_service": matches_service,
                "service_uuids": service_uuids,
            }
        )

    rows.sort(key=lambda row: row["rssi"], reverse=True)

    if not rows:
        print("No matching BLE devices found.")
        print("Tips:")
        print("- Wake up Frame and keep it near the Mac")
        print("- Disconnect it from phone or other computers")
        print("- Make sure Terminal or iTerm has Bluetooth permission")
        return

    print(f"Found {len(rows)} device(s):")
    for index, row in enumerate(rows, start=1):
        print(f"[{index}] {row['name']}")
        print(f"    address: {row['address']}")
        print(f"    rssi: {row['rssi']}")
        print(f"    tx_power: {row['tx_power']}")
        print(f"    frame_service: {row['matches_service']}")
        if row["service_uuids"]:
            print(f"    services: {', '.join(row['service_uuids'])}")


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(scan(args.timeout, args.name_contains, args.show_all))


if __name__ == "__main__":
    main()
