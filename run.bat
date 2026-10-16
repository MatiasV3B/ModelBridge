@echo off
title Antigravity Bridge
cd /d "%~dp0"
call "%~dp0resolve-python.bat"
if not exist "%PYW%" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -NoLaunch
call "%~dp0resolve-python.bat"
:: con consola: python.exe en lugar de pythonw.exe
set "PY=%PYW:pythonw.exe=python.exe%"
"%PY%" main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ocurrio un error al ejecutar Antigravity Bridge.
    pause
)
