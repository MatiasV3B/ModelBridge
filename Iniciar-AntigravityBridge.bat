@echo off
title Antigravity Bridge
cd /d "%~dp0"

:: Primera ejecucion: crear el entorno aislado (.venv) con uv
if not exist ".venv\Scripts\pythonw.exe" (
    echo Preparando Antigravity Bridge por primera vez...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -NoLaunch
)

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" main.py
    exit /b 0
)

echo.
echo ========================================================
echo  Error al iniciar Antigravity Bridge.
echo  Ejecuta Instalador-AntigravityBridge.bat y vuelve a intentar.
echo ========================================================
pause
