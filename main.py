"""Main entry point for Antigravity Bridge application."""

import os
import sys
import argparse
import uvicorn

# Protect against pythonw None stdout/stderr
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from core.config import bridge_config
from server.app import app


def main():
    parser = argparse.ArgumentParser(description="Antigravity Bridge - OpenAI Localhost Gateway")
    parser.add_argument("--headless", "--nogui", action="store_true", dest="headless", help="Run in headless server mode without GUI")
    parser.add_argument("--host", type=str, default=None, help="Host to bind (default from config)")
    parser.add_argument("--port", type=int, default=None, help="Port to bind (default from config)")
    args = parser.parse_args()

    host = args.host or bridge_config.host
    port = args.port or bridge_config.port

    if args.headless:
        print(f"[+] Starting Antigravity Bridge (Headless Server) on http://{host}:{port}/v1")
        print(f"[*] Default model: {bridge_config.default_model}")
        config = uvicorn.Config(app=app, host=host, port=port, log_config=None, loop="asyncio")
        server = uvicorn.Server(config)
        server.run()
    else:
        # Launch Windows GUI
        from gui.app_gui import run_gui
        run_gui()


if __name__ == "__main__":
    main()
