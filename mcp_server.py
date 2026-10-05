#!/usr/bin/env python3
"""Autono Browser MCP Server (Stdio Transport).

Allows external local AI agents (Claude Code, Claude Desktop, Cursor, etc.)
to automate and execute tasks in the user's active Chrome browser session
via Model Bridge.

Usage in claude_desktop_config.json:
{
  "mcpServers": {
    "autono-browser": {
      "command": "python",
      "args": ["d:/Matias/OneDrive/Documentos/GitHub/AntigravityBridge/mcp_server.py"]
    }
  }
}
"""

import sys
import json
import urllib.request
import urllib.error
import os

BRIDGE_URL = os.environ.get("MODEL_BRIDGE_URL", "http://127.0.0.1:8000")


def send_response(data: dict):
    line = json.dumps(data)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def forward_to_bridge(request_data: dict) -> dict:
    url = f"{BRIDGE_URL}/mcp"
    req_bytes = json.dumps(request_data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_bytes,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=75) as response:
            res_bytes = response.read()
            return json.loads(res_bytes.decode("utf-8"))
    except urllib.error.URLError as e:
        msg_id = request_data.get("id")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32603,
                "message": f"Could not connect to Model Bridge on {BRIDGE_URL}. Make sure Model Bridge is running: {e}"
            }
        }
    except Exception as e:
        msg_id = request_data.get("id")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32603,
                "message": f"Error communicating with Model Bridge: {e}"
            }
        }


def main():
    # Stdio loop for MCP JSON-RPC
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            try:
                request_data = json.loads(line)
            except json.JSONDecodeError:
                send_response({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"}
                })
                continue

            response = forward_to_bridge(request_data)
            if response:
                send_response(response)

        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as e:
            sys.stderr.write(f"MCP stdio server error: {e}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
