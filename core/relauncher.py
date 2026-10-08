"""Hard restart of the Bridge.

The running Bridge starts this file as a detached helper and then exits. The helper kills whatever is
still alive of this folder's Bridge (the old process, leftovers that keep port 8765 busy, CLI children)
and starts a fresh one. It lives in its own process because a process cannot relaunch itself after it died.

Usage: python relauncher.py <parent_pid> <port> <cwd> -- <command...>
"""

import os
import socket
import subprocess
import sys
import time

WIN = os.name == "nt"


def _log(msg: str) -> None:
    try:
        folder = os.path.join(os.path.expanduser("~"), ".antigravity_bridge")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "restart.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}" + chr(10))
    except Exception:
        pass


def _port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _kill(pid: int) -> None:
    if pid == os.getpid():
        return
    try:
        if WIN:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=15,
                           creationflags=0x08000000)
        else:
            os.kill(pid, 9)
    except Exception:
        pass


def _stray_bridges(root: str):
    """PIDs of other processes running this folder's main.py (a Bridge that survived)."""
    main_py = os.path.join(root, "main.py")
    found = []
    try:
        if WIN:
            script = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and "
                      "$_.CommandLine.IndexOf($env:BRIDGE_MAIN, [StringComparison]::OrdinalIgnoreCase) -ge 0 } "
                      "| ForEach-Object { $_.ProcessId }")
            out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                                 timeout=30, creationflags=0x08000000, env={**os.environ, "BRIDGE_MAIN": main_py}).stdout
            found = [int(x) for x in out.split() if x.isdigit()]
        else:
            out = subprocess.run(["pgrep", "-f", main_py], capture_output=True, text=True, timeout=10).stdout
            found = [int(x) for x in out.split() if x.isdigit()]
    except Exception:
        pass
    return [p for p in found if p != os.getpid()]


def main() -> int:
    parent_pid, port, cwd = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    command = sys.argv[sys.argv.index("--") + 1:]
    time.sleep(1.0)  # let the old Bridge finish answering the request that asked for the restart

    # no /T: the helper is a child of the old Bridge and must survive it
    _kill(parent_pid)
    strays = _stray_bridges(cwd)
    _log(f"parent={parent_pid} strays={strays}")
    for pid in strays:
        _kill(pid)

    deadline = time.time() + 20
    while _port_busy(port) and time.time() < deadline:
        time.sleep(0.4)

    flags = 0
    kwargs = {}
    if WIN:
        flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    _log(f"port busy={_port_busy(port)} starting {command}")
    subprocess.Popen(command, cwd=cwd, creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
