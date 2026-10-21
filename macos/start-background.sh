#!/bin/bash
source "$(dirname "$0")/python.sh"
cd "$BRIDGE_DIR"
mkdir -p "$HOME/.antigravity_bridge"
nohup "$PY" main.py --headless >> "$HOME/.antigravity_bridge/background.log" 2>&1 &
echo "Antigravity Bridge iniciado en segundo plano (http://127.0.0.1:8765)."
