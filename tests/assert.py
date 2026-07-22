#!/usr/bin/env python3
"""
Dotfiles assertion suite — Linux, macOS, Windows, and WSL.

This script is a thin orchestrator. The actual checks live in `tests/helpers/`
and are grouped by feature (ssh, core, unix, windows). Run a single feature
in isolation like so:

    cd tests
    python3 -c "from helpers.runner import Runner; \\
               from helpers.platform import Platform, detect_platform; \\
               from helpers.ssh import assert_ssh_config; \\
               from pathlib import Path; \\
               r = Runner(); \\
               assert_ssh_config(r, Path.home(), detect_platform()); \\
               raise SystemExit(r.summary())"

Usage:
    python3 tests/assert.py              # auto-detects platform
    python3 tests/assert.py --platform linux
    python3 tests/assert.py --platform darwin
    python3 tests/assert.py --platform wsl
    python3 tests/assert.py --platform windows
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make `helpers` importable whether the script is run as `python3 tests/assert.py`
# (cwd = repo root) or `python3 assert.py` from inside `tests/`.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from helpers.core import (  # noqa: E402
    assert_chezmoi_config,
    assert_core_dotfiles,
    assert_core_tools,
    assert_rtk_extensions,
)
from helpers.platform import Platform, detect_platform  # noqa: E402
from helpers.runner import Runner  # noqa: E402
from helpers.ssh import assert_ssh_config  # noqa: E402
from helpers.unix import (  # noqa: E402
    assert_bashrc,
    assert_profile_dev,
    assert_terminator,
    assert_wsl_gitconfig,
    assert_zshrc,
)
from helpers.pi import assert_pi_cli  # noqa: E402
from helpers.windows import (  # noqa: E402
    assert_windows_dotfiles,
    assert_windows_terminal,
    assert_windows_tools,
)


# ── Test suites (orchestrators) ────────────────────────────────────────────

def run_common(r: Runner, home: Path, platform: Platform) -> None:
    """Assertions that apply on every platform."""
    assert_chezmoi_config(r, home)
    assert_core_dotfiles(r, home)
    assert_core_tools(r)
    assert_rtk_extensions(r, home, platform)
    assert_pi_cli(r)


def run_unix(r: Runner, home: Path, platform: Platform) -> None:
    """Linux / WSL / macOS assertions (shared unix stack)."""
    run_common(r, home, platform)

    r.section(f"{platform.value.title()} dotfiles")
    if platform.is_wsl:
        assert_wsl_gitconfig(r, home)

    assert_zshrc(r, home)
    assert_bashrc(r, home)
    assert_profile_dev(r, home)
    assert_terminator(r, home)
    assert_ssh_config(r, home, platform)

    r.section(f"{platform.value.title()} tools")
    r.assert_command("zsh")


def run_windows(r: Runner, home: Path) -> None:
    """Windows assertions."""
    run_common(r, home, Platform.WINDOWS)
    assert_windows_dotfiles(r, home)
    assert_windows_terminal(r, home)
    assert_windows_tools(r)


# ── Entry point ────────────────────────────────────────────────────────────

def _parse_platform(value: str) -> Platform:
    try:
        return Platform(value)
    except ValueError as exc:
        valid = ", ".join(p.value for p in Platform)
        raise SystemExit(f"Invalid platform {value!r}. Choose from: {valid}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Dotfiles assertion suite")
    parser.add_argument(
        "--platform",
        choices=[p.value for p in Platform],
        default=None,
        help="Override platform detection (default: auto-detect)",
    )
    args = parser.parse_args()

    platform: Platform = _parse_platform(args.platform) if args.platform else detect_platform()
    print(f"Platform: {platform.value}")

    r = Runner()

    if platform.is_windows:
        home = Path(os.environ.get("USERPROFILE", str(Path.home())))
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        # Prepend mise shims so installed tools are reachable during checks
        extra_paths = [
            str(Path(local_app_data) / "mise" / "shims"),
            str(home / "bin"),
        ]
        os.environ["PATH"] = os.pathsep.join(extra_paths) + os.pathsep + os.environ.get("PATH", "")
        run_windows(r, home)
    else:
        home = Path.home()
        # Prepend mise shims so installed tools are reachable during checks
        extra_paths = [
            str(home / ".local" / "bin"),
            str(home / ".local" / "share" / "mise" / "shims"),
        ]
        os.environ["PATH"] = os.pathsep.join(extra_paths) + os.pathsep + os.environ.get("PATH", "")
        run_unix(r, home, platform)

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
