@echo off
title Instalador - Antigravity Bridge
cd /d "%~dp0"
echo ========================================================
echo       INSTALADOR DE ANTIGRAVITY BRIDGE PARA WINDOWS     
echo ========================================================
echo.
echo Instalando CLI, SDK, dependencias y accesos directos...
echo.
powershell -ExecutionPolicy Bypass -File .\install.ps1
pause
