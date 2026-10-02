@echo off
title Instalador de Antigravity Bridge
cd /d "%~dp0"
echo ========================================================
echo       INSTALADOR DE ANTIGRAVITY BRIDGE PARA WINDOWS     
echo ========================================================
echo.
powershell -ExecutionPolicy Bypass -File .\install.ps1
pause
