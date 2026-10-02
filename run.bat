@echo off
title Antigravity Bridge
cd /d "%~dp0"
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ocurrio un error al ejecutar Antigravity Bridge.
    pause
)
