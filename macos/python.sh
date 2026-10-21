#!/bin/bash
# Lo usan los otros scripts con "source". Deja en PY el Python de este Bridge:
#   - modo seguro: el del .venv de la carpeta
#   - modo normal: el Python del sistema que guardo install.sh en .python-path
BRIDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$BRIDGE_DIR/.venv/bin/python"
[ -f "$BRIDGE_DIR/.python-path" ] && PY="$(head -n1 "$BRIDGE_DIR/.python-path")"
if [ ! -x "$PY" ]; then
    echo "Preparando Antigravity Bridge por primera vez..."
    bash "$BRIDGE_DIR/install.sh" --no-launch
    PY="$BRIDGE_DIR/.venv/bin/python"
    [ -f "$BRIDGE_DIR/.python-path" ] && PY="$(head -n1 "$BRIDGE_DIR/.python-path")"
fi
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
