"""Run HomeClaw's dependency-free verification suites.

Examples:
    python scripts/verify.py --suite unit
    python scripts/verify.py --suite smoke
    python scripts/verify.py --suite all
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def run_unit() -> None:
    _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"])


def run_smoke() -> None:
    for script in sorted((ROOT / "tests").glob("smoke_*.py")):
        _run([sys.executable, str(script)])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=("unit", "smoke", "all"), default="all")
    args = parser.parse_args()

    if args.suite in ("unit", "all"):
        run_unit()
    if args.suite in ("smoke", "all"):
        run_smoke()


if __name__ == "__main__":
    main()
