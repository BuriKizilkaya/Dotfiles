# dotfiles

Personal dotfiles managed with [chezmoi](https://www.chezmoi.io/). Supports Linux, macOS, Windows, and WSL.

## Structure

```
dotfiles/
├── home/                          # chezmoi source directory (mirrors $HOME)
│   ├── dot_gitconfig.tmpl         # ~/.gitconfig
│   ├── dot_zshrc                  # ~/.zshrc
│   ├── dot_bashrc                 # ~/.bashrc
│   ├── dot_profile.dev.tmpl       # ~/.profile.dev (shell helpers & aliases)
│   ├── dot_chezmoi.toml.tmpl      # chezmoi config template
│   ├── .chezmoiignore             # platform-conditional file exclusions
│   ├── .chezmoiremove             # files chezmoi should delete from $HOME
│   ├── .chezmoiscripts/           # lifecycle automation scripts
│   │   ├── run_before_01_install-zsh.sh.tmpl         # zsh + plugins (Linux/macOS)
│   │   ├── run_after_02_mise-install.sh.tmpl          # mise install (Linux/macOS)
│   │   ├── run_after_02_mise-install.ps1.tmpl         # mise install (Windows)
│   │   ├── run_after_init-powershell-profile_windows.ps1.tmpl
│   │   ├── run_once_init-mise-config.sh.tmpl
│   │   └── run_once_init-mise-config_windows.ps1.tmpl
│   └── dot_config/
│       ├── mise/conf.d/common.toml     # mise tool versions (all platforms)
│       ├── starship.toml               # shell prompt (all platforms)
│       ├── terminator/config           # Linux only
│       ├── powershell/                 # Windows only
│       │   ├── Microsoft.PowerShell_profile.ps1
│       │   └── Install-Modules.ps1
│       └── windows-terminal/           # Windows only
│           └── settings.json
├── tests/
│   ├── assert.py                  # cross-platform assertion suite
│   ├── Dockerfile                 # Ubuntu 24.04 test image
│   ├── run-devcontainer-tests.sh  # runs Docker-based tests
│   └── run-wsl-tests.ps1          # runs tests in a temporary WSL distro
├── bootstrap.sh                   # Linux/macOS bootstrap
├── bootstrap.ps1                  # Windows bootstrap
└── bootstrap_devcontainer.sh      # devcontainer/CI bootstrap
```

---

## Installation

### Linux

**Requirements**

```bash
sudo apt-get install -y curl git zsh unzip ca-certificates
```

**Bootstrap**

```bash
DOTFILES_ENV=dev_computer bash bootstrap.sh
```

> `DOTFILES_ENV` options: `dev_computer` (default) · `home_lab` · `devcontainer`

`bootstrap.sh` installs mise, installs chezmoi through mise, writes the chezmoi config, symlinks the repo, and runs `chezmoi apply`. The `run_after` hooks then install mise tools and configure zsh with plugins.

---

### macOS

**Requirements**

```bash
xcode-select --install       # provides git and curl
```

**Bootstrap**

```bash
DOTFILES_ENV=dev_computer bash bootstrap.sh
```

---

### Windows

**Requirements**

- [Git for Windows](https://git-scm.com/download/win)
- [PowerShell 7+](https://aka.ms/powershell)

**Bootstrap** (run PowerShell as Administrator)

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
.\bootstrap.ps1
```

`bootstrap.ps1` installs mise via `winget`, installs chezmoi through mise, writes the chezmoi config, symlinks the repo, and runs `chezmoi apply`. The `run_after` hooks then install mise tools and set up the PowerShell profile.

> Windows always uses `DOTFILES_ENV=dev_computer`.

---

### WSL

Inside your WSL distribution, follow the **Linux** steps above.

The gitconfig template automatically sets `sshCommand = ssh.exe` so git uses your Windows SSH agent — no separate SSH key setup is needed inside WSL.

---

## How it works

- **chezmoi** manages all files under `home/` and applies them to `$HOME`
- Files prefixed with `dot_` map to dotfiles (e.g. `dot_zshrc` → `~/.zshrc`)
- Files ending in `.tmpl` are Go templates rendered per-machine (OS, env, username, etc.)
- `run_before_*` scripts run before files are applied; `run_after_*` scripts run after
- `.chezmoiignore` excludes platform-specific files on other platforms (e.g. PowerShell files are skipped on Linux/macOS)

### Adding new dotfiles

```bash
chezmoi add ~/.someconfig
chezmoi edit ~/.someconfig
chezmoi apply
```

---

## Testing

### Linux / devcontainer (Docker)

```bash
bash tests/run-devcontainer-tests.sh
```

Builds a clean Ubuntu 24.04 Docker image, runs `bootstrap_devcontainer.sh`, then runs `tests/assert.py`.

### WSL

```powershell
pwsh tests/run-wsl-tests.ps1
# Optional flags:
pwsh tests/run-wsl-tests.ps1 -Branch my-branch -DotfilesEnv dev_computer
```

Imports a temporary Ubuntu WSL distro, bootstraps dotfiles from the current branch, runs `tests/assert.py --platform wsl`, then removes the distro.

### CI

All platforms are tested automatically on every push and pull request to `main` via GitHub Actions: Linux, macOS, devcontainer, Windows, and WSL.

---

## Tools configured

| Tool             | Config file                         | Platforms    |
| ---------------- | ----------------------------------- | ------------ |
| git              | `~/.gitconfig`                      | All          |
| zsh + plugins    | `~/.zshrc`                          | Linux, macOS |
| bash             | `~/.bashrc`                         | Linux, macOS |
| Shell helpers    | `~/.profile.dev`                    | Linux, macOS |
| mise             | `~/.config/mise/conf.d/common.toml` | All          |
| starship         | `~/.config/starship.toml`           | All          |
| Terminator       | `~/.config/terminator/config`       | Linux        |
| PowerShell       | `~/.config/powershell/`             | Windows      |
| Windows Terminal | `~/.config/windows-terminal/`       | Windows      |
