"""Unix (Linux + macOS) shell & profile assertions."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from helpers.platform import Platform
from helpers.runner import Runner


def assert_zshrc(r: Runner, home: Path) -> None:
    r.section("zsh")
    r.assert_file(home / ".zshrc")
    r.assert_file_contains(home / ".zshrc", "starship init zsh")
    r.assert_file_contains(home / ".zshrc", "mise activate")
    r.assert_file_contains(home / ".zshrc", "zoxide init zsh")
    r.assert_file_not_contains(home / ".zshrc", "SSH_AUTH_SOCK")
    r.assert_command_succeeds(["zsh", "-lc", 'source "$HOME/.zshrc"'], "Source ~/.zshrc")


def assert_bashrc(r: Runner, home: Path) -> None:
    r.section("bash")
    r.assert_file(home / ".bashrc")
    r.assert_file_contains(home / ".bashrc", "starship init bash")
    r.assert_file_contains(home / ".bashrc", "mise activate")
    r.assert_file_contains(home / ".bashrc", "zoxide init bash")
    r.assert_file_not_contains(home / ".bashrc", "SSH_AUTH_SOCK")


def assert_profile_dev(r: Runner, home: Path, platform: Platform) -> None:
    r.section("Profile (.profile.dev)")
    profile_dev = home / ".profile.dev"
    dotfiles_env = os.environ.get("DOTFILES_ENV", "dev_computer")

    r.assert_file(profile_dev)
    r.assert_file_contains(profile_dev, "groot")
    r.assert_file_contains(profile_dev, "alias isodate")

    if dotfiles_env == "devcontainer" or platform.is_wsl:
        r.assert_file_not_contains(profile_dev, "SSH_AUTH_SOCK")
        r.assert_file_not_contains(profile_dev, "1password/agent.sock")
        r.assert_file_not_contains(profile_dev, "2BUA8C4S2C.com.1password")
    elif platform.is_macos:
        r.assert_file_contains(profile_dev, "SSH_AUTH_SOCK")
        r.assert_file_contains(profile_dev, "2BUA8C4S2C.com.1password")
    elif platform.is_linux:
        r.assert_file_contains(profile_dev, "SSH_AUTH_SOCK")
        r.assert_file_contains(profile_dev, "$HOME/.1password/agent.sock")


def assert_profile_template_rendering(r: Runner) -> None:
    r.section("Profile template rendering")

    def render_profile(os_name: str, env: str, osrelease: str) -> str:
        repo_root = Path(__file__).resolve().parents[2]
        profile_template = repo_root / "home" / "dot_profile.dev.tmpl"
        override_data = json.dumps(
            {
                "chezmoi": {
                    "os": os_name,
                    "kernel": {"osrelease": osrelease},
                },
                "env": env,
            }
        )
        result = subprocess.run(
            ["chezmoi", "execute-template", "--override-data", override_data],
            input=profile_template.read_text(encoding="utf-8"),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip()
            r._fail(f"Render .profile.dev template for {os_name}/{env}: {details}")
            return ""
        return result.stdout

    darwin_profile = render_profile("darwin", "dev_computer", "Darwin Kernel Version")
    r.assert_text_contains(darwin_profile, "SSH_AUTH_SOCK", "macOS profile exports SSH_AUTH_SOCK")
    r.assert_text_contains(
        darwin_profile,
        "2BUA8C4S2C.com.1password/t/agent.sock",
        "macOS profile uses 1Password macOS socket",
    )
    r.assert_text_not_contains(
        darwin_profile,
        "$HOME/.1password/agent.sock",
        "macOS profile skips Linux 1Password socket",
    )

    linux_profile = render_profile("linux", "dev_computer", "generic-linux")
    r.assert_text_contains(linux_profile, "SSH_AUTH_SOCK", "Linux profile exports SSH_AUTH_SOCK")
    r.assert_text_contains(
        linux_profile,
        "$HOME/.1password/agent.sock",
        "Linux profile uses 1Password Linux socket",
    )
    r.assert_text_not_contains(
        linux_profile,
        "2BUA8C4S2C.com.1password",
        "Linux profile skips macOS 1Password socket",
    )

    devcontainer_profile = render_profile("linux", "devcontainer", "generic-linux")
    r.assert_text_not_contains(devcontainer_profile, "SSH_AUTH_SOCK", "devcontainer profile skips SSH_AUTH_SOCK")
    r.assert_text_not_contains(
        devcontainer_profile,
        "1password/agent.sock",
        "devcontainer profile skips 1Password sockets",
    )
    r.assert_text_not_contains(
        devcontainer_profile,
        "2BUA8C4S2C.com.1password",
        "devcontainer profile skips macOS 1Password socket",
    )

    wsl_profile = render_profile("linux", "dev_computer", "microsoft-standard-WSL2")
    r.assert_text_not_contains(wsl_profile, "SSH_AUTH_SOCK", "WSL profile skips SSH_AUTH_SOCK")
    r.assert_text_not_contains(wsl_profile, "1password/agent.sock", "WSL profile skips 1Password sockets")
    r.assert_text_not_contains(
        wsl_profile,
        "2BUA8C4S2C.com.1password",
        "WSL profile skips macOS 1Password socket",
    )


def assert_terminator(r: Runner, home: Path) -> None:
    r.section("Terminator")
    r.assert_file(home / ".config/terminator/config")
    r.assert_file_contains(home / ".config/terminator/config", "background_color")


def assert_wsl_gitconfig(r: Runner, home: Path) -> None:
    """WSL routes SSH through the Windows host (ssh.exe alias)."""
    r.assert_file_contains(home / ".gitconfig", "sshCommand = ssh.exe")
