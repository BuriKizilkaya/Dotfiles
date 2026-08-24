# Bootstrap script for Windows (PowerShell)
# Usage: .\bootstrap.ps1
#
# This script only does the minimum needed to get chezmoi running.
# Everything else (mise tools, etc.) is handled by chezmoi hooks
# in home/run_once_* and home/run_onchange_* — run automatically by `chezmoi apply`.

$ErrorActionPreference = "Stop"

$DotfilesDir = $PSScriptRoot

# Windows is always a dev_computer environment.
$env:DOTFILES_ENV = "dev_computer"
Write-Host "==> Environment: $env:DOTFILES_ENV" -ForegroundColor Cyan

Write-Host "==> Installing mise..." -ForegroundColor Cyan
if (Get-Command mise -ErrorAction SilentlyContinue) {
    Write-Host "  mise already installed, skipping." -ForegroundColor Green
} else {
    winget install --id jdx.mise --silent --accept-source-agreements --accept-package-agreements
    $env:PATH = "$env:LOCALAPPDATA\mise\shims;$env:PATH"
}

Write-Host "==> Installing chezmoi with mise..." -ForegroundColor Cyan
mise use -g chezmoi@latest

Write-Host "==> Applying dotfiles..." -ForegroundColor Cyan

# Write chezmoi config so the environment is persisted for future runs.
$ChezmoiConfigDir = "$env:USERPROFILE\.config\chezmoi"
New-Item -ItemType Directory -Force -Path $ChezmoiConfigDir | Out-Null
@"
[data]
    env = "$env:DOTFILES_ENV"
"@ | Set-Content -Path "$ChezmoiConfigDir\chezmoi.toml" -Encoding UTF8

# Symlink ~/.local/share/chezmoi -> dotfiles repo root so that chezmoi cd
# lands in the git root. .chezmoiroot tells chezmoi the source files are in
# the home/ subdirectory.
$ChezmoiShareDir = "$env:USERPROFILE\.local\share"
New-Item -ItemType Directory -Force -Path $ChezmoiShareDir | Out-Null
$ChezmoiLink = "$ChezmoiShareDir\chezmoi"
if (Test-Path $ChezmoiLink) {
    Remove-Item $ChezmoiLink -Force -Recurse
}
New-Item -ItemType SymbolicLink -Path $ChezmoiLink -Target $DotfilesDir | Out-Null

# chezmoi apply runs all dotfiles + the run_once_/run_onchange_ hooks
mise exec chezmoi@latest -- chezmoi apply

Write-Host ""
Write-Host "Done! Restart your terminal to apply changes." -ForegroundColor Green
