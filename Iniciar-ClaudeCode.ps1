# Antigravity Bridge - Claude Code Launcher (PowerShell)
$Host.UI.RawUI.WindowTitle = "Claude Code - Terminal CLI"

$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8765"
if (-not $env:ANTHROPIC_API_KEY) {
    $env:ANTHROPIC_API_KEY = "sk-antigravity"
}

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "  CLAUDE CODE - TERMINAL CLI (ANTIGRAVITY BRIDGE)" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  [+] Base URL:  $($env:ANTHROPIC_BASE_URL)" -ForegroundColor White
Write-Host "  [+] API Key:   $($env:ANTHROPIC_API_KEY)" -ForegroundColor White
Write-Host ""
Write-Host "  Modelos Antigravity (Google Auth):" -ForegroundColor Yellow
Write-Host "    * claude-sonnet-4-6 (Sonnet 4.6 Thinking)"
Write-Host "    * claude-opus-4-6-thinking (Opus 4.6 Thinking)"
Write-Host "    * gemini-3.8-flash-high / medium / low"
Write-Host ""
Write-Host "  Modelos Claude Code:" -ForegroundColor Yellow
Write-Host "    * claude-sonnet-5-5, claude-opus-5-5, claude-fable-5-1, claude-haiku-4-5"
Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Bridge is running on port 8765
$tcp = New-Object Net.Sockets.TcpClient
$isConnected = $false
try {
    $tcp.Connect("127.0.0.1", 8765)
    $isConnected = $true
    $tcp.Close()
} catch {
    $isConnected = $false
}

if (-not $isConnected) {
    Write-Host "[i] Iniciando Antigravity Bridge en segundo plano..." -ForegroundColor Gray
    $VenvPythonw = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
    if (-not (Test-Path $VenvPythonw)) {
        & (Join-Path $PSScriptRoot "install.ps1") -NoLaunch
    }
    Start-Process -FilePath $VenvPythonw -ArgumentList "main.py --headless" -WorkingDirectory $PSScriptRoot
    Start-Sleep -Seconds 2
}

if ($args.Count -eq 0) {
    Write-Host "[i] Iniciando sesion interactiva de Claude Code..." -ForegroundColor Green
    & claude
} else {
    & claude @args
}
