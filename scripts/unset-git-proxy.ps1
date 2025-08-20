# This script unsets Git HTTP/HTTPS proxy ONLY for this repository.
# It uses the parent folder of this script (repo root) so you can double-click to run.

$RepoRoot = Split-Path $PSScriptRoot -Parent
Write-Host "Unsetting Git local proxy for repo: $RepoRoot" -ForegroundColor Cyan

# Unset local proxy (repo scope); ignore errors if not set
git -C $RepoRoot config --unset http.proxy -ErrorAction SilentlyContinue
git -C $RepoRoot config --unset https.proxy -ErrorAction SilentlyContinue

Write-Host "Current proxy settings (should be empty or none):" -ForegroundColor Yellow
git -C $RepoRoot config -l | Select-String proxy | ForEach-Object { $_.ToString() }

Write-Host "Done. Local proxy removed for this repo." -ForegroundColor Green