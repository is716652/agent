<#
修复/重建虚拟环境脚本（Windows/PowerShell）

用途：当项目迁移到新电脑后，VENV\agent-env\pyvenv.cfg 中记录的 Python 安装路径与版本
      与新电脑不一致，导致虚拟环境无法激活。本脚本用于“修复 pyvenv.cfg”或“删除重建 venv”。

用法示例：
  1) 仅修复路径（默认）：
     powershell -NoProfile -ExecutionPolicy Bypass -File scripts/repair-venv.ps1

  2) 指定 Python 解释器路径修复：
     powershell -NoProfile -ExecutionPolicy Bypass -File scripts/repair-venv.ps1 -PythonExe "C:\\Users\\me\\Python\\Python312\\python.exe"

  3) 重建虚拟环境（推荐在主/次版本不一致时）：
     powershell -NoProfile -ExecutionPolicy Bypass -File scripts/repair-venv.ps1 -Recreate -Force

参数：
  -VenvPath   默认 "VENV\\agent-env"
  -PythonExe  指定用于修复/重建的 Python 解释器路径
  -Recreate   直接删除并重建虚拟环境
  -Force      删除重建时跳过确认；或在版本不一致时继续尝试修复
#>

param(
  [string]$VenvPath = "VENV\agent-env",
  [string]$PythonExe = "",
  [switch]$Recreate,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
  if ($PSScriptRoot) { return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
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
  throw "未找到可用的 Python 解释器，请使用 -PythonExe 指定路径"
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
      Write-Host "将删除并重建虚拟环境: $venvFull (使用 -Force 跳过确认)" -ForegroundColor Yellow
      $yn = Read-Host "确认删除? (y/N)"
      if ($yn.ToLower() -ne "y") { throw "已取消" }
    }
    Remove-Item -Recurse -Force $venvFull
  }
  & $python -m venv $venvFull
  if ($LASTEXITCODE -ne 0) { throw "创建 venv 失败" }
  $venvPython = Join-Path $venvFull "Scripts\\python.exe"
  & $venvPython -m pip install -U pip
  if (Test-Path (Join-Path $repoRoot "requirements.txt")) {
    & $venvPython -m pip install -r (Join-Path $repoRoot "requirements.txt")
  }
  Write-Host "虚拟环境已重建并安装依赖：$venvFull" -ForegroundColor Green
  exit 0
}

if (!(Test-Path $pyvenvCfg)) { throw "未找到 $pyvenvCfg，请使用 -Recreate 重建" }

# 读取现有配置
$cfg = Get-Content $pyvenvCfg -Raw
$lines = $cfg -split "`r?`n"
$dict = @{}
foreach($line in $lines){
  if ($line -match "^\s*([^#][^=]+?)\s*=\s*(.*)$") {
    $k=$matches[1].Trim(); $v=$matches[2].Trim(); $dict[$k]=$v
  }
}
$oldVersion = $dict["version"]
$oldMM = if ($oldVersion) { $oldVersion -replace '^(\d+\.\d+).*','$1' } else { "" }

if ($oldMM -and $oldMM -ne $newMM) {
  Write-Warning "虚拟环境 Python 主版本不一致（旧: $oldVersion, 新: $newVersion）。推荐使用 -Recreate 重建。"
  if (-not $Force) { throw "请使用 -Recreate -Force 进行重建" }
}

# 写回新的路径/版本
$dict["home"] = $newHome
$dict["executable"] = $python
$dict["version"] = $newVersion
$dict["command"] = "$python -m venv $venvFull"

$newLines = @()
foreach($line in $lines){
  if ($line -match "^\s*([^#][^=]+?)\s*=\s*(.*)$") {
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

# 保存（使用 ASCII/CRLF）
Set-Content -Path $pyvenvCfg -Value (($newLines -join "`r`n") + "`r`n") -Encoding ascii

# 简单验证
$venvPython = Join-Path $venvFull "Scripts\\python.exe"
if (!(Test-Path $venvPython)) {
  Write-Warning "未找到 $venvPython；若修复后仍不可用，请使用 -Recreate 重建。"
  exit 1
}
& $venvPython -c "import sys;print('VENV OK:', sys.executable)"
Write-Host "已修复 pyvenv.cfg。若仍无法激活，请使用 -Recreate 重建。" -ForegroundColor Green