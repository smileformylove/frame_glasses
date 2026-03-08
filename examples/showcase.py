import argparse
import subprocess
import sys
from pathlib import Path
from typing import List


SECTIONS = {
    "say": ["say", "--", "--text", "Hello from showcase", "--dry-run"],
    "meeting": ["meeting", "--", "--demo", "--dry-run", "--render-mode", "unicode"],
    "vision": ["vision", "--", "--source", "demo", "--analyzer", "mock", "--mock-result", "Showcase vision demo works.", "--dry-run"],
    "tap-vision": ["tap-vision", "--", "--demo", "--analyzer", "mock", "--mock-result", "Showcase tap vision demo works."],
    "memory": ["memory", "--", "remember", "--source", "demo", "--analyzer", "mock", "--mock-result", "Showcase memory desk.", "--note", "This is the showcase memory desk"],
    "voice": ["voice", "--", "--demo", "--dry-run", "--source", "demo", "--demo-commands", "help|describe this|remember this as showcase desk|recall this|exit", "--analyzer", "mock", "--mock-result", "Detected a showcase desk."],
    "voice-codex": ["voice-codex", "--", "--demo", "--dry-run", "--demo-commands", "help|doctor|git status|ask codex summarize this repo|exit"],
    "frame-mic-live": ["frame-mic-live", "--", "--demo", "--dry-run"],
}
DEFAULT_ORDER = ["say", "meeting", "vision", "tap-vision", "memory", "voice", "voice-codex", "frame-mic-live"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a curated sequence of dry-run demos for the Frame project")
    parser.add_argument("--list", action="store_true", help="List showcase sections and exit")
    parser.add_argument("--sections", default=",".join(DEFAULT_ORDER), help="Comma-separated sections to run")
    return parser


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def section_names(raw: str) -> List[str]:
    names = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [name for name in names if name not in SECTIONS]
    if unknown:
        raise SystemExit(f"Unknown showcase section(s): {', '.join(unknown)}")
    return names


def run_section(name: str) -> int:
    command = [sys.executable, str(repo_root() / 'frame_lab.py'), *SECTIONS[name]]
    print(f"\n=== showcase:{name} ===", flush=True)
    return subprocess.run(command, cwd=repo_root()).returncode


def main() -> None:
    args = build_parser().parse_args()
    if args.list:
        for name in DEFAULT_ORDER:
            print(name)
        return

    for name in section_names(args.sections):
        return_code = run_section(name)
        if return_code != 0:
            raise SystemExit(return_code)


if __name__ == "__main__":
    main()
