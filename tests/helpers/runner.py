"""Test runner with an accumulator pattern — all assertions run, errors collected."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


class Runner:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    # -- primitives --

    def _pass(self, msg: str) -> None:
        print(f"  [PASS] {msg}")
        self.passed += 1

    def _fail(self, msg: str) -> None:
        print(f"  [FAIL] {msg}", file=sys.stderr)
        self.failed += 1
        self.errors.append(msg)

    def skip(self, msg: str) -> None:
        print(f"  [SKIP] {msg}")

    def section(self, title: str) -> None:
        bar = "-" * (68 - len(title))
        print(f"\n-- {title} {bar}")

    # -- assertions --

    def assert_file(self, path: "str | Path") -> None:
        p = Path(path)
        if p.is_file():
            self._pass(f"File exists: {p}")
        else:
            self._fail(f"File missing: {p}")

    def assert_file_contains(self, path: "str | Path", pattern: str) -> None:
        p = Path(path)
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = ""
        if p.is_file() and pattern in content:
            self._pass(f"File {p.name} contains {pattern!r}")
        else:
            self._fail(f"File {p} does not contain {pattern!r}")

    def assert_command(self, cmd: str) -> None:
        if shutil.which(cmd):
            self._pass(f"Command available: {cmd}")
        else:
            self._fail(f"Command not found: {cmd}")

    def assert_command_succeeds(self, cmd: list[str], msg: str) -> None:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            self._pass(msg)
        else:
            details = (result.stderr or result.stdout).strip()
            suffix = f": {details}" if details else ""
            self._fail(f"{msg}{suffix}")

    def assert_symlink(self, path: "str | Path") -> None:
        p = Path(path)
        if p.is_symlink():
            self._pass(f"Symlink exists: {p}")
        else:
            self._fail(f"Symlink missing: {p}")

    def assert_file_absent(self, path: "str | Path") -> None:
        p = Path(path)
        if not p.exists():
            self._pass(f"File absent: {p}")
        else:
            self._fail(f"File should not exist: {p}")

    def assert_file_not_contains(self, path: "str | Path", pattern: str) -> None:
        p = Path(path)
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = ""
        if p.is_file() and pattern not in content:
            self._pass(f"File {p.name} does not contain {pattern!r}")
        else:
            self._fail(f"File {p} unexpectedly contains {pattern!r}")

    # -- summary --

    def summary(self) -> int:
        """Print result summary and return an exit code (0 = all pass)."""
        print()
        print("-" * 70)
        print(f"  Results: {self.passed} passed, {self.failed} failed")
        if self.errors:
            print("\n  Failed checks:")
            for e in self.errors:
                print(f"    - {e}")
            print()
            return 1
        print()
        return 0
