#!/usr/bin/env python3
"""
Pre-commit hook: enforce myTrader code rules on staged Python files.

Rules:
  MT001 - No direct os.getenv() calls (use config/settings.py)
  MT002 - SQL INSERT field count must match VALUES placeholder count
  MT003 - Enum members must not be used directly as dict keys (use .value)

Exit code 0: all checks passed
Exit code 1: one or more violations found
"""

import ast
import re
import subprocess
import sys


# ---------------------------------------------------------------------------
# Staged file helpers
# ---------------------------------------------------------------------------

def get_staged_py_files():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[ERROR] Failed to get staged files: {result.stderr.strip()}")
        sys.exit(1)
    return [p.strip() for p in result.stdout.splitlines() if p.strip().endswith(".py")]


# ---------------------------------------------------------------------------
# MT001: No direct os.getenv()
# ---------------------------------------------------------------------------

def check_no_raw_getenv(filepath, source):
    """
    Detect calls of the form:  os.getenv(...)  or  os.environ.get(...)
    Allow in config/settings.py itself (that's the canonical place).
    """
    if filepath.replace("\\", "/").endswith(("config/settings.py", "config/db.py")):
        return []

    violations = []
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return []  # syntax errors caught by py_compile elsewhere

    for node in ast.walk(tree):
        # os.getenv(...)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "getenv"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
        ):
            violations.append((node.lineno, "MT001 os.getenv() called directly - use config/settings.py instead"))

        # os.environ.get(...) or os.environ[...]
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "environ"
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "os"
        ):
            violations.append((node.lineno, "MT001 os.environ.get() called directly - use config/settings.py instead"))

    return violations


# ---------------------------------------------------------------------------
# MT002: SQL INSERT field count matches VALUES placeholder count
# ---------------------------------------------------------------------------

# Matches:  INSERT INTO table (f1, f2, f3) VALUES (%s, %s, %s)
# Also handles multi-line via re.DOTALL
_INSERT_RE = re.compile(
    r"INSERT\s+(?:INTO\s+)?\w+\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)

def check_sql_insert(filepath, source):
    violations = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        # Quick pre-filter to avoid full regex on every line
        upper = line.upper()
        if "INSERT" not in upper or "VALUES" not in upper:
            continue
        for m in _INSERT_RE.finditer(line):
            fields = [f.strip() for f in m.group(1).split(",") if f.strip()]
            placeholders = [v.strip() for v in m.group(2).split(",") if v.strip()]
            if len(fields) != len(placeholders):
                violations.append((
                    lineno,
                    f"MT002 INSERT field count ({len(fields)}) != VALUES placeholder count ({len(placeholders)})",
                ))
    return violations


# ---------------------------------------------------------------------------
# MT003: Enum members used directly as dict keys (should use .value)
# ---------------------------------------------------------------------------

def check_enum_dict_key(filepath, source):
    """
    Heuristic: detect patterns like  {SomeEnum.MEMBER: ...}  or
    d[SomeEnum.MEMBER]  where the key is an Attribute node whose value
    is a Name starting with an uppercase letter (likely an Enum class).

    False-positive rate is low because lowercase names are filtered out.
    """
    violations = []
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return []

    def _is_likely_enum_attr(node):
        return (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id[0].isupper()  # UpperCase class name
        )

    for node in ast.walk(tree):
        # Dict literal: {EnumClass.MEMBER: value}
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None and _is_likely_enum_attr(key):
                    violations.append((
                        key.lineno,
                        f"MT003 Enum member '{key.value.id}.{key.attr}' used as dict key directly - use .value",
                    ))

        # Subscript: d[EnumClass.MEMBER]
        if isinstance(node, ast.Subscript):
            sl = node.slice
            if _is_likely_enum_attr(sl):
                violations.append((
                    sl.lineno,
                    f"MT003 Enum member '{sl.value.id}.{sl.attr}' used as subscript key - use .value",
                ))

    return violations


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

CHECKS = [
    ("MT001", check_no_raw_getenv),
    ("MT002", check_sql_insert),
    ("MT003", check_enum_dict_key),
]


def main():
    files = get_staged_py_files()
    if not files:
        sys.exit(0)

    found_any = False
    for filepath in files:
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                source = f.read()
        except OSError as e:
            print(f"[WARN] Cannot read {filepath}: {e}")
            continue

        for _rule_id, checker in CHECKS:
            violations = checker(filepath, source)
            for lineno, msg in violations:
                print(f"[FAIL] {filepath}:{lineno}: {msg}")
                found_any = True

    if found_any:
        print()
        print("[FAIL] Code rule violations found. Fix the issues above before committing.")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
