@echo off
title Antigravity Bridge
cd /d "%~dp0"

:: Primera ejecucion: preparar Python (entorno aislado con uv, o el Python del sistema en modo normal)
call "%~dp0resolve-python.bat"
if not exist "%PYW%" echo Preparando Antigravity Bridge por primera vez...
if not exist "%PYW%" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -NoLaunch
call "%~dp0resolve-python.bat"

if exist "%PYW%" (
    start "" "%PYW%" main.py
    exit /b 0
)

echo.
echo ========================================================
echo  Error al iniciar Antigravity Bridge.
echo  Ejecuta Instalador-AntigravityBridge.bat y vuelve a intentar.
echo ========================================================
pause
