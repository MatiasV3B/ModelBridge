#!/bin/bash
PLUGIN_DIR="$HOME/.gemini/config/plugins/googlecloudtools.datacloud_telemetry"
if [ -d "$PLUGIN_DIR" ]; then
    rm -rf "$PLUGIN_DIR"
    echo "[OK] Carpeta googlecloudtools.datacloud_telemetry eliminada correctamente."
else
    echo "[INFO] La carpeta ya no existe."
fi
