@echo off
title Antigravity Bridge - Claude Code Terminal

:: Configurar variables de entorno para Claude Code
set ANTHROPIC_BASE_URL=http://127.0.0.1:8000
if "%ANTHROPIC_API_KEY%"=="" set ANTHROPIC_API_KEY=sk-antigravity

echo =====================================================================
echo   CLAUDE CODE (TERMINAL) VIA ANTIGRAVITY BRIDGE
echo =====================================================================
echo.
echo   [+] Base URL:  %ANTHROPIC_BASE_URL%
echo   [+] API Key:   %ANTHROPIC_API_KEY%
echo.
echo   Modelos Antigravity (Google Auth):
echo     * claude-sonnet-4-6 (Sonnet 4.6 Thinking)
echo     * claude-opus-4-6-thinking (Opus 4.6 Thinking)
echo     * gemini-3.8-flash-high / medium / low
echo.
echo   Modelos Claude Code:
echo     * claude-sonnet-5-5, claude-opus-5-5, claude-fable-5-1, claude-haiku-4-5
echo.
echo =====================================================================
echo.

:: Verificar si el servidor Antigravity Bridge esta en ejecucion en el puerto 8000
powershell -NoProfile -Command "$s = New-Object Net.Sockets.TcpClient; try { $s.Connect('127.0.0.1', 8000); $s.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [i] Iniciando Antigravity Bridge en segundo plano...
    start /b pythonw "%~dp0main.py" --headless >nul 2>&1
    timeout /t 2 /nobreak >nul
)

:: Ejecutar Claude Code
if "%~1"=="" (
    echo [i] Iniciando sesion interactiva de Claude Code...
    claude
) else (
    claude %*
)
