"""Fail when tracked source files are not valid UTF-8."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".bat", ".css", ".editorconfig", ".html", ".js", ".json", ".md",
    ".mjs", ".py", ".scss", ".sh", ".toml", ".ts", ".tsx", ".vue",
    ".yaml", ".yml",
}
EXCLUDED_PARTS = {".git", "dist", "node_modules", "static"}


def tracked_text_files():
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = ROOT / raw_path.decode("utf-8")
        if path.suffix.lower() in TEXT_SUFFIXES and not EXCLUDED_PARTS.intersection(path.parts):
            yield path


def main() -> int:
    errors = []
    for path in tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{path.relative_to(ROOT)}: invalid UTF-8 ({exc})")
            continue

        if "\ufffd" in text:
            errors.append(f"{path.relative_to(ROOT)}: contains Unicode replacement character")

    if errors:
        print("UTF-8 validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("UTF-8 validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
