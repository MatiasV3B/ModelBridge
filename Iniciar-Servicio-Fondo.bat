@echo off
cd /d "%~dp0"

if exist "C:\Python314\pythonw.exe" (
    start "" "C:\Python314\pythonw.exe" main.py --headless
) else (
    start "" pythonw main.py --headless
)
exit /b 0
