param(
  [string]$Proxy = "http://127.0.0.1:10808"
)

# This script sets Git HTTP/HTTPS proxy ONLY for this repository.
# It uses the parent folder of this script (repo root) so you can double-click to run.
# If Windows blocks the script, right-click the file and choose "Run with PowerShell".

$RepoRoot = Split-Path $PSScriptRoot -Parent
Write-Host "Setting Git local proxy for repo: $RepoRoot -> $Proxy" -ForegroundColor Cyan

# Configure local proxy (repo scope)
git -C $RepoRoot config http.proxy $Proxy
git -C $RepoRoot config https.proxy $Proxy

Write-Host "Effective proxy settings:" -ForegroundColor Green
git -C $RepoRoot config -l | Select-String proxy | ForEach-Object { $_.ToString() }

Write-Host "Done. You can now git fetch/pull/push in this repo using the proxy." -ForegroundColor Green