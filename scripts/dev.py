"""Shared local and CI checks: test, lint, check, package-check."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def run(arguments: list[str]) -> int:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return subprocess.call([sys.executable, *arguments], cwd=ROOT, env=env)


def test(arguments: list[str]) -> int:
    work = ROOT / ".review-work"
    work.mkdir(exist_ok=True)
    temporary = tempfile.mkdtemp(prefix="pytest-", dir=work)
    return run(["-m", "pytest", "-p", "no:cacheprovider", f"--basetemp={temporary}", *arguments])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("test", "lint", "check", "package-check"))
    args, extra = parser.parse_known_args()
    if extra[:1] == ["--"]:
        extra = extra[1:]
    if args.command == "test":
        return test(extra)
    if args.command == "lint":
        return run(["-m", "ruff", "check", ".", *extra])
    if args.command == "package-check":
        return run([str(ROOT / "scripts" / "check_distribution.py"), *extra])
    if extra:
        parser.error("check does not accept extra arguments")
    return run(["-m", "ruff", "check", "."]) or test([])


if __name__ == "__main__":
    raise SystemExit(main())
