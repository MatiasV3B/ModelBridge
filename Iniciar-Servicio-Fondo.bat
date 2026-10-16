@echo off
cd /d "%~dp0"

call "%~dp0resolve-python.bat"
if not exist "%PYW%" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -NoLaunch
call "%~dp0resolve-python.bat"
start "" "%PYW%" main.py --headless
exit /b 0
