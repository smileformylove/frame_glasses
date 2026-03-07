import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]

PYTHON_PACKAGES = {
    "frame_ble": "frame-ble",
    "frame_msg": "frame-msg",
    "numpy": "numpy",
    "PIL": "Pillow",
    "lz4": "lz4",
    "sounddevice": "sounddevice",
    "faster_whisper": "faster-whisper",
    "openai": "openai",
    "pytesseract": "pytesseract",
}

SYSTEM_TOOLS = {
    "tesseract": "Required for OCR mode",
    "ffmpeg": "Recommended for audio tooling and pyannote support",
    "python3": "Required runtime",
    "git": "Required for version control and push",
}

ENV_VARS = {
    "OPENAI_API_KEY": "Needed for OpenAI translation and vision modes",
    "HUGGINGFACE_TOKEN": "Needed for pyannote speaker diarization",
}


class Reporter:
    def __init__(self) -> None:
        self.failures = 0
        self.warnings = 0

    def ok(self, label: str, detail: str) -> None:
        print(f"OK    {label:<18} {detail}")

    def warn(self, label: str, detail: str) -> None:
        self.warnings += 1
        print(f"WARN  {label:<18} {detail}")

    def fail(self, label: str, detail: str) -> None:
        self.failures += 1
        print(f"FAIL  {label:<18} {detail}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check whether the local environment is ready for Frame development")
    parser.add_argument("--strict", action="store_true", help="Treat missing optional items as failures")
    return parser


def check_python(reporter: Reporter) -> None:
    version = sys.version_info
    if version >= (3, 9):
        reporter.ok("python", f"{version.major}.{version.minor}.{version.micro}")
    else:
        reporter.fail("python", "Python 3.9+ is required")


def check_packages(reporter: Reporter, strict: bool) -> None:
    for module_name, package_name in PYTHON_PACKAGES.items():
        found = importlib.util.find_spec(module_name) is not None
        if found:
            reporter.ok(package_name, "installed")
        else:
            if package_name in ("sounddevice", "faster-whisper", "openai", "pytesseract"):
                (reporter.fail if strict else reporter.warn)(package_name, "not installed")
            else:
                reporter.fail(package_name, "not installed")


def check_tools(reporter: Reporter, strict: bool) -> None:
    for tool, note in SYSTEM_TOOLS.items():
        path = shutil.which(tool)
        if path:
            reporter.ok(tool, path)
        else:
            (reporter.fail if tool in ("python3", "git") or strict else reporter.warn)(tool, note)


def check_env_vars(reporter: Reporter, strict: bool) -> None:
    for env_var, note in ENV_VARS.items():
        if os.environ.get(env_var):
            reporter.ok(env_var, "set")
        else:
            (reporter.fail if strict else reporter.warn)(env_var, note)


def check_fonts(reporter: Reporter, strict: bool) -> None:
    existing = [candidate for candidate in DEFAULT_FONT_CANDIDATES if Path(candidate).exists()]
    if existing:
        reporter.ok("unicode-font", existing[0])
    else:
        (reporter.fail if strict else reporter.warn)("unicode-font", "No default macOS Unicode font found")


def check_repo(reporter: Reporter) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if (repo_root / ".git").exists():
        reporter.ok("git-repo", str(repo_root))
    else:
        reporter.warn("git-repo", "Current folder is not a Git repository")

    readme = repo_root / "README.md"
    if readme.exists():
        reporter.ok("README", str(readme))
    else:
        reporter.fail("README", "README.md not found")

    remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo_root, capture_output=True, text=True)
    if remote.returncode == 0:
        reporter.ok("origin", remote.stdout.strip())
    else:
        reporter.warn("origin", "No git remote named origin")


def print_manual_notes() -> None:
    print("\nManual checks:")
    print("- In macOS, grant Bluetooth access to Terminal or iTerm")
    print("- For meeting/voice commands, grant microphone access to Terminal or iTerm")
    print("- Wake Frame and keep it near the Mac before scanning or connecting")


def main() -> None:
    args = build_parser().parse_args()
    reporter = Reporter()

    check_python(reporter)
    check_packages(reporter, args.strict)
    check_tools(reporter, args.strict)
    check_env_vars(reporter, args.strict)
    check_fonts(reporter, args.strict)
    check_repo(reporter)
    print_manual_notes()

    print(f"\nSummary: {reporter.failures} failure(s), {reporter.warnings} warning(s)")
    raise SystemExit(1 if reporter.failures else 0)


if __name__ == "__main__":
    main()
