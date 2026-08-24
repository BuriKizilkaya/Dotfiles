"""Chezmoi config + core dotfile assertions (apply to every platform)."""

from __future__ import annotations

from pathlib import Path

from helpers.platform import Platform
from helpers.runner import Runner


def assert_chezmoi_config(r: Runner, home: Path) -> None:
    r.section("Chezmoi config")
    r.assert_file(home / ".config/chezmoi/chezmoi.toml")
    r.assert_file_contains(home / ".config/chezmoi/chezmoi.toml", "env")
    r.assert_symlink(home / ".local/share/chezmoi")


def assert_core_dotfiles(r: Runner, home: Path) -> None:
    r.section("Core dotfiles")
    r.assert_file(home / ".gitconfig")
    r.assert_file_contains(home / ".gitconfig", "defaultBranch = main")
    r.assert_file_contains(home / ".gitconfig", "autocrlf = false")

    r.assert_file(home / ".config/starship.toml")
    r.assert_file_contains(home / ".config/starship.toml", "add_newline")

    r.assert_file(home / ".config/mise/config.toml")
    r.assert_file_contains(home / ".config/mise/config.toml", "chezmoi")

    r.assert_file(home / ".config/mise/conf.d/common.toml")
    r.assert_file_contains(home / ".config/mise/conf.d/common.toml", "opencode")
    r.assert_file_contains(home / ".config/mise/conf.d/common.toml", "starship")
    r.assert_file_contains(home / ".config/mise/conf.d/common.toml", "eza")
    r.assert_file_contains(home / ".config/mise/conf.d/common.toml", "ripgrep")
    r.assert_file_contains(home / ".config/mise/conf.d/common.toml", "fd")
    r.assert_file_contains(home / ".config/mise/conf.d/common.toml", "pi")
    r.assert_file_contains(home / ".config/mise/conf.d/common.toml", "rtk-ai/rtk")
    r.assert_file_contains(home / ".config/mise/conf.d/common.toml", "rtk init -g --opencode")
    r.assert_file_contains(home / ".config/mise/conf.d/common.toml", "rtk init -g --agent pi")


def assert_core_tools(r: Runner) -> None:
    r.section("Core tools")
    r.assert_command("chezmoi")
    r.assert_command("git")
    r.assert_command("mise")
    r.assert_command("starship")
    r.assert_command("rg")
    r.assert_command("fd")


def assert_rtk_extensions(r: Runner, home: Path, platform: Platform) -> None:
    r.section("rtk extensions")
    # The rtk postinstall in common.toml uses a bash shebang; on Windows the
    # hook can't run, so we only enforce the installed files on unix.
    if platform.is_windows:
        r.skip("rtk postinstall is bash-only; skipped on Windows")
        return
    r.assert_file(home / ".config/opencode/plugins/rtk.ts")
    r.assert_file(home / ".pi/agent/extensions/rtk.ts")
