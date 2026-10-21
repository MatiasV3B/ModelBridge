#!/bin/bash
# Instalador de Antigravity Bridge para macOS (modo seguro con uv o modo normal con pip).
#   0. Si se ejecuta fuera del repo (curl ... | bash), descarga el Bridge a ~/Library/Application Support/AntigravityBridge.
#   1. Verifica e instala el CLI de Antigravity (agy).
#   2. Prepara Python: seguro = .venv aislado con uv (recomendado); normal = pip --user en tu Python 3.10+.
#   3. Comprueba la sesion de Antigravity.
#   4. Crea "Model Bridge.app" en ~/Applications (aparece en Launchpad y Spotlight).
#   5. Inicia la aplicacion.
# Modo: --mode secure|normal  >  BRIDGE_INSTALL_MODE  >  .install-mode  >  pregunta  >  seguro.
#   curl -fsSL https://raw.githubusercontent.com/MatiasV3B/ModelBridge/main/install.sh | bash
set -e

REPO_ZIP="https://github.com/MatiasV3B/ModelBridge/archive/refs/heads/main.zip"
NO_LAUNCH=0
MODE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --no-launch) NO_LAUNCH=1 ;;
        --mode) MODE="$2"; shift ;;
        --mode=*) MODE="${1#--mode=}" ;;
    esac
    shift
done

echo "========================================================"
echo "       ANTIGRAVITY BRIDGE PARA macOS - INSTALADOR       "
echo "========================================================"
echo

# 0. Ubicar el proyecto (o descargarlo)
DIR=""
if [ -n "${BASH_SOURCE[0]}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/main.py" ]; then
    DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ -z "$DIR" ]; then
    DIR="$HOME/Library/Application Support/AntigravityBridge"
    echo "[0/5] Descargando Antigravity Bridge en $DIR ..."
    TMP="$(mktemp -d)"
    curl -fsSL "$REPO_ZIP" -o "$TMP/bridge.zip"
    unzip -q "$TMP/bridge.zip" -d "$TMP"
    mkdir -p "$DIR"
    rsync -a --exclude .venv --exclude .git --exclude .env "$TMP"/ModelBridge-main/ "$DIR"/
    rm -rf "$TMP"
    echo "  [OK] Descarga completada."
fi
cd "$DIR"
MODE_FILE="$DIR/.install-mode"
PYTHON_FILE="$DIR/.python-path"

resolve_mode() {
    for m in "$MODE" "$BRIDGE_INSTALL_MODE"; do
        if [ "$m" = "secure" ] || [ "$m" = "normal" ]; then echo "$m"; return; fi
    done
    if [ -f "$MODE_FILE" ]; then
        saved="$(tr -d '[:space:]' < "$MODE_FILE")"
        if [ "$saved" = "secure" ] || [ "$saved" = "normal" ]; then echo "$saved"; return; fi
    fi
    if [ "$NO_LAUNCH" = "0" ] && [ -r /dev/tty ]; then
        {
            echo "Como quieres instalarlo?"
            echo "  [1] Modo seguro (recomendado): entorno aislado (.venv con uv). No toca tu Python ni sus paquetes."
            echo "  [2] Modo normal: usa pip con el Python de tu sistema (--user). Mas simple, pero mezcla paquetes."
        } > /dev/tty
        printf "Elige 1 o 2 [1]: " > /dev/tty
        read -r answer < /dev/tty || true
        case "$answer" in 2|normal|n) echo normal; return ;; esac
    fi
    echo secure
}

INSTALL_MODE="$(resolve_mode)"
echo "Modo de instalacion: $INSTALL_MODE"
echo
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# 1. Antigravity CLI
echo "[1/5] Comprobando Antigravity CLI (agy)..."
if command -v agy >/dev/null 2>&1; then
    echo "  [OK] Antigravity CLI detectado en: $(command -v agy)"
else
    echo "  [..] Antigravity CLI no encontrado. Instalando automaticamente..."
    if curl -fsSL https://antigravity.google/cli/install.sh | bash; then
        echo "  [OK] Antigravity CLI instalado con exito."
    else
        echo "  [!] Advertencia: no se pudo instalar el CLI. Puedes instalarlo despues."
    fi
fi

find_system_python() {
    for c in python3.13 python3.12 python3.11 python3.10 python3; do
        p="$(command -v "$c" 2>/dev/null)" || continue
        if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            "$p" -c 'import sys; print(sys.executable)'; return 0
        fi
    done
    return 1
}

# 2. Python y dependencias
if [ "$INSTALL_MODE" = "normal" ]; then
    echo "[2/5] Instalando dependencias con pip en tu Python (modo normal)..."
    echo "  [!] Esto agrega paquetes al Python de tu usuario y puede cambiar versiones que ya tengas."
    SYS_PY="$(find_system_python)" || { echo "  [!] No se encontro Python 3.10+. Instalalo (brew install python) o usa el modo seguro."; exit 1; }
    echo "  -> Usando $SYS_PY"
    "$SYS_PY" -m pip install --user --disable-pip-version-check -r requirements.txt \
        || "$SYS_PY" -m pip install --user --break-system-packages --disable-pip-version-check -r requirements.txt
    "$SYS_PY" -c "import fastapi, uvicorn, customtkinter, pydantic, PIL, requests" \
        || { echo "  [!] No se pudieron instalar las dependencias. Usa el modo seguro."; exit 1; }
    printf '%s' "$SYS_PY" > "$PYTHON_FILE"
    echo "  [OK] Dependencias instaladas en $SYS_PY"
else
    echo "[2/5] Preparando entorno aislado (uv)..."
    if ! command -v uv >/dev/null 2>&1; then
        echo "  [..] Instalando uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh || true
        export PATH="$HOME/.local/bin:$PATH"
    fi
    command -v uv >/dev/null 2>&1 || { echo "  [!] No se pudo instalar uv. Instalalo con: brew install uv"; exit 1; }
    SYNC="uv sync"
    [ -f uv.lock ] && SYNC="uv sync --frozen"
    if ! $SYNC; then
        echo "  [!] uv no pudo usar su propio Python. Probando con el Python del sistema..."
        SYS_PY="$(find_system_python)" && { rm -rf .venv; $SYNC --python "$SYS_PY"; }
    fi
    [ -x .venv/bin/python ] || { echo "  [!] No se pudo crear el entorno. Revisa tu conexion."; exit 1; }
    rm -f "$PYTHON_FILE"
    echo "  [OK] Entorno listo en $DIR/.venv"
fi
printf '%s' "$INSTALL_MODE" > "$MODE_FILE"
chmod +x ./*.sh ./*.command 2>/dev/null || true

# 3. Sesion de Antigravity
echo "[3/5] Comprobando sesion en Google Antigravity..."
if command -v agy >/dev/null 2>&1 && [ "$(agy models 2>/dev/null | wc -l)" -gt 1 ]; then
    echo "  [OK] Sesion activa y verificada en Google Antigravity."
else
    echo "  [!] No se detecto sesion. Podras iniciar sesion con el boton 'Iniciar Sesion' en la aplicacion."
fi

# 4. App en ~/Applications
echo "[4/5] Creando 'Model Bridge.app' en ~/Applications..."
APP="$HOME/Applications/Model Bridge.app"
mkdir -p "$APP/Contents/MacOS"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Model Bridge</string>
  <key>CFBundleIdentifier</key><string>com.matiasv3b.modelbridge.app</string>
  <key>CFBundleExecutable</key><string>ModelBridge</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
</dict></plist>
PLIST
cat > "$APP/Contents/MacOS/ModelBridge" <<LAUNCH
#!/bin/bash
cd "$DIR" && exec ./macos/run-gui.sh
LAUNCH
chmod +x "$APP/Contents/MacOS/ModelBridge"
echo "  [OK] App creada: $APP"

# 5. Lanzar
echo "[5/5] Instalacion completada con exito! (modo $INSTALL_MODE)"
if [ "$NO_LAUNCH" = "0" ]; then
    echo "Iniciando Antigravity Bridge..."
    open "$APP"
    echo "Listo. Para actualizar mas adelante usa Actualizar-AntigravityBridge.command"
fi
