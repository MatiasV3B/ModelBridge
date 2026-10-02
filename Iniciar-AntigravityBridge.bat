@echo off
title Antigravity Bridge
cd /d "%~dp0"

:: Verificar si pythonw esta disponible directamente
where pythonw >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    start "" pythonw main.py
    exit /b 0
)

:: Verificar ruta estándar de Python 3.14
if exist "C:\Python314\pythonw.exe" (
    start "" "C:\Python314\pythonw.exe" main.py
    exit /b 0
)

:: Fallback con python estándar mostrando error si falla
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================================
    echo  Error al iniciar Antigravity Bridge.
    echo  Verifica que las dependencias esten instaladas.
    echo ========================================================
    pause
)
