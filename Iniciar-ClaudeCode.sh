#!/bin/bash
# Antigravity Bridge - Claude Code Launcher (macOS)
DIR="$(cd "$(dirname "$0")" && pwd)"
export ANTHROPIC_BASE_URL="http://127.0.0.1:8765"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-sk-antigravity}"
export PATH="$HOME/.local/bin:$HOME/.claude/local:/opt/homebrew/bin:/usr/local/bin:$PATH"
printf '\033]0;Claude Code - Terminal CLI\007'

echo "====================================================================="
echo "  CLAUDE CODE - TERMINAL CLI (ANTIGRAVITY BRIDGE)"
echo "====================================================================="
echo
echo "  [+] Base URL:  $ANTHROPIC_BASE_URL"
echo "  [+] API Key:   $ANTHROPIC_API_KEY"
echo
echo "  Modelos Antigravity (Google Auth):"
echo "    * claude-sonnet-4-6 (Sonnet 4.6 Thinking)"
echo "    * claude-opus-4-6-thinking (Opus 4.6 Thinking)"
echo "    * gemini-3.8-flash-high / medium / low"
echo
echo "  Modelos Claude Code:"
echo "    * claude-sonnet-5-5, claude-opus-5-5, claude-fable-5-1, claude-haiku-4-5"
echo
echo "====================================================================="
echo

if ! nc -z 127.0.0.1 8765 2>/dev/null; then
    echo "[i] Iniciando Antigravity Bridge en segundo plano..."
    bash "$DIR/macos/start-background.sh" >/dev/null
    sleep 2
fi

if [ $# -eq 0 ]; then
    echo "[i] Iniciando sesion interactiva de Claude Code..."
fi
exec claude "$@"
