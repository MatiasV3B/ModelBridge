<#
.SYNOPSIS
    Compilador a ejecutable independiente .exe para Antigravity Bridge.
#>

$ErrorActionPreference = "Stop"
Write-Host "Compilando Antigravity Bridge con PyInstaller..." -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ScriptDir) { $ScriptDir = Get-Location }

Set-Location $ScriptDir

python -m PyInstaller `
    --noconfirm `
    --onedir `
    --windowed `
    --name "AntigravityBridge" `
    --add-data "core;core" `
    --add-data "server;server" `
    --add-data "gui;gui" `
    --hidden-import "uvicorn" `
    --hidden-import "fastapi" `
    --hidden-import "customtkinter" `
    --hidden-import "google.antigravity" `
    main.py

Write-Host "Compilación finalizada. El ejecutable se encuentra en dist/AntigravityBridge/AntigravityBridge.exe" -ForegroundColor Green
