#!/usr/bin/env python3
"""
Pre-commit hook: check for emoji characters in staged .py, .md, .csv files.

MySQL utf8 charset does not support 4-byte emoji characters.
Any emoji in code, comments, CSV, logs, or Markdown will cause write failures.

Exit code 0: no emoji found (OK)
Exit code 1: emoji found (FAIL)
"""

import re
import subprocess
import sys


# Emoji Unicode ranges (4-byte / supplementary plane characters)
# Main emoji block: U+1F000 - U+1FFFF
# Supplemental symbols: U+2600 - U+27FF (2-byte but rendered as emoji)
# Enclosed alphanumeric supplement: U+1F100 - U+1F1FF
# Misc symbols and pictographs: U+1F300 - U+1F5FF
# Transport and map symbols: U+1F680 - U+1F6FF
# Supplemental symbols and pictographs: U+1F900 - U+1F9FF
# Symbols and pictographs extended-A: U+1FA00 - U+1FAFF
# Dingbats (partial): U+2702 - U+27B0
# Variation selectors: used with emoji
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F000-\U0001FFFF"  # Main 4-byte emoji range (covers most)
    "\U0001F900-\U0001F9FF"  # Supplemental symbols and pictographs
    "\U0001FA00-\U0001FAFF"  # Symbols and pictographs extended-A
    "\U00002600-\U000026FF"  # Misc symbols (sun, star, cloud, etc.)
    "\U00002700-\U000027BF"  # Dingbats (scissors, pencil, etc.)
    "]",
    flags=re.UNICODE,
)

TARGET_EXTENSIONS = {".py", ".md", ".csv"}


def get_staged_files():
    """Return list of staged file paths filtered by target extensions."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[ERROR] Failed to get staged files: {result.stderr.strip()}")
        sys.exit(1)

    files = []
    for path in result.stdout.splitlines():
        path = path.strip()
        if not path:
            continue
        ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
        if ext.lower() in TARGET_EXTENSIONS:
            files.append(path)
    return files


def check_file_for_emoji(filepath):
    """
    Check a single file for emoji characters.
    Returns list of (line_number, line_content) tuples where emoji found.
    """
    violations = []
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, start=1):
                if EMOJI_PATTERN.search(line):
                    violations.append((lineno, line.rstrip()))
    except OSError as e:
        print(f"[WARN] Cannot read {filepath}: {e}")
    return violations


def main():
    staged_files = get_staged_files()
    if not staged_files:
        sys.exit(0)

    found_any = False
    for filepath in staged_files:
        violations = check_file_for_emoji(filepath)
        if violations:
            found_any = True
            for lineno, line in violations:
                # Show up to 120 chars of the offending line
                preview = line[:120]
                print(f"[EMOJI] {filepath}:{lineno}: {preview}")

    if found_any:
        print()
        print("[FAIL] Emoji characters detected in staged files.")
        print("       MySQL utf8 charset does not support 4-byte emoji.")
        print("       Replace emoji with plain-text markers such as [OK], [WARN], [RED].")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
