<#
VENV repair/recreate script (Windows/PowerShell)

Purpose:
- When the project is moved to a new machine, the recorded Python path/version in
  VENV\agent-env\pyvenv.cfg may not match the new Python installation, causing venv activation to fail.
- This script fixes pyvenv.cfg paths or recreates the venv.

Usage examples:
  1) Repair paths only (default):
     powershell -NoProfile -ExecutionPolicy Bypass -File scripts/repair-venv.ps1

  2) Repair with a specified Python executable:
     powershell -NoProfile -ExecutionPolicy Bypass -File scripts/repair-venv.ps1 -PythonExe "C:\\Users\\me\\Python\\Python312\\python.exe"

  3) Recreate the venv (recommended when Python major/minor versions differ):
     powershell -NoProfile -ExecutionPolicy Bypass -File scripts/repair-venv.ps1 -Recreate -Force

Parameters:
  -VenvPath   default "VENV\\agent-env"
  -PythonExe  specify Python interpreter path
  -Recreate   delete and recreate the virtual environment
  -Force      skip confirmation when recreating; or continue even when versions differ
#>

param(
  [string]$VenvPath = "VENV\agent-env",
  [string]$PythonExe = "",
  [switch]$Recreate,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
  if ($PSScriptRoot) { return (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path }
  return (Get-Location).Path
}

function Find-Python {
  param([string]$Preferred)
  if ($Preferred -and (Test-Path $Preferred)) { return (Resolve-Path $Preferred).Path }
  $candidates = @(
    { & py -3.12 -c "import sys;print(sys.executable)" 2>$null },
    { & py -3 -c "import sys;print(sys.executable)" 2>$null },
    { & python -c "import sys;print(sys.executable)" 2>$null },
    { & python3 -c "import sys;print(sys.executable)" 2>$null }
  )
  foreach($c in $candidates){
    try { $out = & $c; if ($LASTEXITCODE -eq 0 -and $out) { return $out.Trim() } } catch {}
  }
  throw "No usable Python interpreter found. Please pass -PythonExe to specify one."
}

$repoRoot = Resolve-RepoRoot
$venvFull = Join-Path $repoRoot $VenvPath
$pyvenvCfg = Join-Path $venvFull "pyvenv.cfg"

$python = Find-Python -Preferred $PythonExe
$newVersion = & $python -c "import sys;print('%d.%d.%d'%sys.version_info[:3])"
$newMM = & $python -c "import sys;print('%d.%d'%sys.version_info[:2])"
$newHome = Split-Path -Parent $python

if (!(Test-Path $venvFull)) { $Recreate = $true }

if ($Recreate) {
  if (Test-Path $venvFull) {
    if (-not $Force) {
      Write-Host "The virtual environment will be deleted and recreated: $venvFull (use -Force to skip confirm)" -ForegroundColor Yellow
      $yn = Read-Host "Confirm delete? (y/N)"
      if ($yn.ToLower() -ne "y") { throw "Cancelled" }
    }
    Remove-Item -Recurse -Force $venvFull
  }
  & $python -m venv $venvFull
  if ($LASTEXITCODE -ne 0) { throw "Failed to create venv" }
  $venvPython = Join-Path $venvFull "Scripts\python.exe"
  & $venvPython -m pip install -U pip
  if (Test-Path (Join-Path $repoRoot "requirements.txt")) {
    & $venvPython -m pip install -r (Join-Path $repoRoot "requirements.txt")
  }
  Write-Host "Venv recreated and dependencies installed: $venvFull" -ForegroundColor Green
  exit 0
}

if (!(Test-Path $pyvenvCfg)) { throw "Not found: $pyvenvCfg, please use -Recreate to rebuild venv" }

# Read existing config
$cfg = Get-Content $pyvenvCfg -Raw
$lines = $cfg -split "`r?`n"
$dict = @{}
foreach($line in $lines){
  if ($line -match '^\s*([^#][^=]+?)\s*=\s*(.*)$') {
    $k=$matches[1].Trim(); $v=$matches[2].Trim(); $dict[$k]=$v
  }
}
$oldVersion = $dict["version"]
$oldMM = if ($oldVersion) { $oldVersion -replace '^(\d+\.\d+).*','$1' } else { "" }

if ($oldMM -and $oldMM -ne $newMM) {
  Write-Warning "Python major/minor version mismatch (old: $oldVersion, new: $newVersion). It is recommended to use -Recreate."
  if (-not $Force) { throw "Please run with -Recreate -Force to rebuild the venv" }
}

# Write back new paths/versions
$dict["home"] = $newHome
$dict["executable"] = $python
$dict["version"] = $newVersion
$dict["command"] = "$python -m venv $venvFull"

$newLines = @()
foreach($line in $lines){
  if ($line -match '^\s*([^#][^=]+?)\s*=\s*(.*)$') {
    $k=$matches[1].Trim()
    if ($dict.ContainsKey($k)) {
      $newLines += "$k = $($dict[$k])"
      $dict.Remove($k)
    } else {
      $newLines += $line
    }
  } else {
    $newLines += $line
  }
}
foreach($k in $dict.Keys){ $newLines += "$k = $($dict[$k])" }

# Save (ASCII/CRLF)
Set-Content -Path $pyvenvCfg -Value (($newLines -join "`r`n") + "`r`n") -Encoding ascii

# Basic validation
$venvPython = Join-Path $venvFull "Scripts\python.exe"
if (!(Test-Path $venvPython)) {
  Write-Warning "Not found: $venvPython. If activation still fails, please run with -Recreate."
  exit 1
}
& $venvPython -c "import sys;print('VENV OK:', sys.executable)"
Write-Host "pyvenv.cfg repaired. If activation still fails, please run with -Recreate." -ForegroundColor Green