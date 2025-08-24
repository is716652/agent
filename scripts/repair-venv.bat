@echo off
setlocal ENABLEDELAYEDEXPANSION
set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%repair-venv.ps1" %*
endlocal