"""Single verification entry point: lint, format check, and byte-compile.

Usage: python scripts/verify.py
Exits non-zero if any step fails. Works on Windows, macOS and Linux.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

STEPS: list[list[str]] = [
    [sys.executable, "-m", "ruff", "check", "."],
    [sys.executable, "-m", "ruff", "format", "--check", "."],
    [sys.executable, "-m", "compileall", "-q", "server", "client"],
]


def main() -> int:
    for cmd in STEPS:
        print(f"$ {' '.join(cmd[1:])}", flush=True)
        result = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
        if result.returncode != 0:
            print(f"verify: FAILED at: {' '.join(cmd[1:])}", file=sys.stderr)
            return result.returncode or 1
    print("verify: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
