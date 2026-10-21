#!/bin/bash
# Cierra el Bridge de esta carpeta (con su .venv o con el Python del sistema). No toca otros programas Python.
BRIDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
pkill -f "$BRIDGE_DIR/main.py" 2>/dev/null
pkill -f "$BRIDGE_DIR/.venv/bin/python" 2>/dev/null
# Lo que se inicio con ruta relativa (cd + "python main.py")
for pid in $(pgrep -f "main.py"); do
    cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')"
    [ "$cwd" = "$BRIDGE_DIR" ] && kill "$pid" 2>/dev/null
done
exit 0
