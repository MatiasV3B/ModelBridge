#!/bin/bash
# Actualiza Antigravity Bridge en macOS: cierra el Bridge, baja el codigo nuevo (git pull o ZIP),
# sincroniza Python con install.sh en el MISMO modo (.install-mode) y lo vuelve a iniciar.
#   ./update.sh [--no-restart]
set -e
REPO_ZIP="https://github.com/MatiasV3B/ModelBridge/archive/refs/heads/main.zip"
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
echo "=== Actualizando Antigravity Bridge ==="

bash "$DIR/macos/stop-background.sh"

if [ -d .git ] && command -v git >/dev/null 2>&1; then
    echo "[1/3] git pull..."
    git pull --ff-only || { echo "git pull fallo. Resuelve los cambios locales y vuelve a intentar."; exit 1; }
else
    echo "[1/3] Descargando la ultima version..."
    TMP="$(mktemp -d)"
    curl -fsSL "$REPO_ZIP" -o "$TMP/bridge.zip"
    unzip -q "$TMP/bridge.zip" -d "$TMP"
    rsync -a --exclude .venv --exclude .git --exclude .env "$TMP"/ModelBridge-main/ "$DIR"/
    rm -rf "$TMP"
fi

echo "[2/3] Sincronizando dependencias..."
bash "$DIR/install.sh" --no-launch

if [ "$1" != "--no-restart" ]; then
    echo "[3/3] Iniciando Antigravity Bridge..."
    source "$DIR/macos/python.sh"
    nohup "$PY" "$DIR/main.py" >/dev/null 2>&1 &
fi
echo "[OK] Antigravity Bridge actualizado."
