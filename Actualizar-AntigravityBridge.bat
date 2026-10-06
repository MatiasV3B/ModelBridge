@echo off
title Actualizar Antigravity Bridge
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ocurrio un error durante la actualizacion.
)
pause
