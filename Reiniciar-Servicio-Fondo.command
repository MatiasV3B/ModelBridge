#!/bin/bash
# Reinicio completo: cierra el Bridge del todo (incluido lo que ocupe el puerto) y lo abre de nuevo.
DIR="$(cd "$(dirname "$0")" && pwd)"
bash "$DIR/macos/stop-background.sh"
sleep 2
bash "$DIR/macos/start-background.sh"
