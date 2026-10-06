@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -NoLaunch
)
start "" ".venv\Scripts\pythonw.exe" main.py --headless
exit /b 0
