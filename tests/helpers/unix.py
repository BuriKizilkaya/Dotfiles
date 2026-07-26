"""Unix (Linux + macOS) shell & profile assertions."""

from __future__ import annotations

from pathlib import Path

from helpers.platform import Platform
from helpers.runner import Runner


def assert_zshrc(r: Runner, home: Path) -> None:
    r.section("zsh")
    r.assert_file(home / ".zshrc")
    r.assert_file_contains(home / ".zshrc", "starship init zsh")
    r.assert_file_contains(home / ".zshrc", "mise activate")
    r.assert_file_contains(home / ".zshrc", "zoxide init zsh")
    r.assert_command_succeeds(["zsh", "-lc", 'source "$HOME/.zshrc"'], "Source ~/.zshrc")


def assert_bashrc(r: Runner, home: Path) -> None:
    r.section("bash")
    r.assert_file(home / ".bashrc")
    r.assert_file_contains(home / ".bashrc", "starship init bash")
    r.assert_file_contains(home / ".bashrc", "mise activate")
    r.assert_file_contains(home / ".bashrc", "zoxide init bash")


def assert_profile_dev(r: Runner, home: Path) -> None:
    r.section("Profile (.profile.dev)")
    r.assert_file(home / ".profile.dev")
    r.assert_file_contains(home / ".profile.dev", "groot")
    r.assert_file_contains(home / ".profile.dev", "alias isodate")


def assert_terminator(r: Runner, home: Path) -> None:
    r.section("Terminator")
    r.assert_file(home / ".config/terminator/config")
    r.assert_file_contains(home / ".config/terminator/config", "background_color")


def assert_wsl_gitconfig(r: Runner, home: Path) -> None:
    """WSL routes SSH through the Windows host (ssh.exe alias)."""
    r.assert_file_contains(home / ".gitconfig", "sshCommand = ssh.exe")
