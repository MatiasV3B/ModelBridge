#!/bin/bash
source "$(dirname "$0")/python.sh"
cd "$BRIDGE_DIR" && exec "$PY" main.py
