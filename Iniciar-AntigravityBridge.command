#!/bin/bash
# Abre la ventana de Antigravity Bridge (doble clic en Finder).
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/macos/python.sh"
cd "$DIR" && nohup "$PY" main.py >/dev/null 2>&1 &
exit 0
