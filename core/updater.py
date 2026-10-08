"""Updates for the Bridge and for the Autono extension, straight from their GitHub repos.

- "Is there something new?" compares the latest commit on GitHub with what is installed here.
- A git clone is updated with `git pull --ff-only`; anything else (a downloaded ZIP) gets the repo ZIP laid over it.
- The extension is a folder Chrome loaded ("Load unpacked"); its path is read from the Chrome profile, so the
  user never has to say where it is.
"""

import glob
import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from typing import Optional

logger = logging.getLogger("antigravity_bridge")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(os.path.expanduser("~"), ".antigravity_bridge")
STATE_FILE = os.path.join(STATE_DIR, "updates.json")

BRIDGE_REPO = "MatiasV3B/ModelBridge"
EXTENSION_REPO = "MatiasV3B/Autono"
EXTENSION_SUBDIR = "Autono"  # the folder inside the extension repo that Chrome loads

_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_latest_cache = {}  # repo -> (timestamp, sha)
CACHE_SECONDS = 120


def _load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def _git(args, cwd, timeout=60) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout,
                              creationflags=_NO_WINDOW)
    except Exception:
        return None


def _git_root(path: str) -> Optional[str]:
    """The git clone this folder belongs to, if any."""
    probe = os.path.abspath(path)
    for _ in range(3):
        if os.path.isdir(os.path.join(probe, ".git")):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    return None


def latest_sha(repo: str, force: bool = False) -> str:
    cached = _latest_cache.get(repo)
    if cached and not force and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1]
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/commits/main",
                                 headers={"Accept": "application/vnd.github.sha", "User-Agent": "antigravity-bridge"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        sha = resp.read().decode("ascii").strip()
    _latest_cache[repo] = (time.time(), sha)
    return sha


def _check(key: str, repo: str, folder: str, force: bool) -> dict:
    """Compare what is installed in `folder` with GitHub. `key` names the baseline in the state file."""
    result = {"installed": None, "latest": None, "update_available": False, "method": "zip", "error": None}
    try:
        result["latest"] = latest_sha(repo, force)
    except Exception as exc:
        result["error"] = f"Could not reach GitHub: {exc}"
        return result

    clone = _git_root(folder)
    if clone:
        result["method"] = "git"
        head = _git(["rev-parse", "HEAD"], clone)
        result["installed"] = head.stdout.strip() if head and head.returncode == 0 else None
        _git(["fetch", "--quiet", "origin", "main"], clone, timeout=40)
        behind = _git(["rev-list", "--count", "HEAD..origin/main"], clone)
        try:
            result["update_available"] = bool(behind and behind.returncode == 0 and int(behind.stdout.strip()) > 0)
        except ValueError:
            result["update_available"] = bool(result["installed"] and result["installed"] != result["latest"])
        return result

    state = _load_state()
    installed = state.get(key)
    if not installed:
        # First time we look at a ZIP install: today's version is the baseline
        state[key] = result["latest"]
        _save_state(state)
        installed = result["latest"]
    result["installed"] = installed
    result["update_available"] = installed != result["latest"]
    return result


# ---------------------------------------------------------------------------- the extension's folder

def _chrome_profiles():
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA", "")
    roots = [
        os.path.join(local, "Google", "Chrome", "User Data"),
        os.path.join(local, "Google", "Chrome Beta", "User Data"),
        os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data"),
        os.path.join(local, "Microsoft", "Edge", "User Data"),
        os.path.join(home, "Library", "Application Support", "Google", "Chrome"),
        os.path.join(home, ".config", "google-chrome"),
        os.path.join(home, ".config", "chromium"),
    ]
    for root in roots:
        if os.path.isdir(root):
            yield from glob.glob(os.path.join(root, "*", "Preferences"))
            yield from glob.glob(os.path.join(root, "*", "Secure Preferences"))


def find_extension_folder(ext_id: str) -> Optional[str]:
    """Where Chrome loaded this unpacked extension from (read from the profile's preferences)."""
    if not ext_id or not ext_id.isalnum():
        return None
    for prefs in _chrome_profiles():
        try:
            with open(prefs, encoding="utf-8") as f:
                settings = json.load(f).get("extensions", {}).get("settings", {})
            path = (settings.get(ext_id) or {}).get("path")
            if path and os.path.isfile(os.path.join(path, "manifest.json")):
                return os.path.abspath(path)
        except Exception:
            continue
    return None


def resolve_extension_folder(ext_id: str, ext_path: str = "") -> Optional[str]:
    """The profile tells us; if it does not (another browser), the folder the user typed in Settings is used."""
    folder = find_extension_folder(ext_id)
    if not folder and ext_path and os.path.isfile(os.path.join(ext_path, "manifest.json")):
        folder = os.path.abspath(ext_path)
    return folder


def status(ext_id: str = "", force: bool = False, ext_path: str = "") -> dict:
    out = {"bridge": _check("bridge", BRIDGE_REPO, ROOT, force), "extension": None, "extension_folder": None}
    folder = resolve_extension_folder(ext_id, ext_path)
    out["extension_folder"] = folder
    if folder:
        out["extension"] = _check("extension", EXTENSION_REPO, folder, force)
    else:
        out["extension"] = {"installed": None, "latest": None, "update_available": False, "method": None,
                            "error": "Could not find the folder Chrome loaded the extension from. Type it in Settings → Updates."}
        try:
            out["extension"]["latest"] = latest_sha(EXTENSION_REPO, force)
        except Exception:
            pass
    return out


# ------------------------------------------------------------------------------------ applying

def _download_zip(repo: str) -> zipfile.ZipFile:
    req = urllib.request.Request(f"https://github.com/{repo}/archive/refs/heads/main.zip",
                                 headers={"User-Agent": "antigravity-bridge"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return zipfile.ZipFile(io.BytesIO(resp.read()))


def _overlay(zf: zipfile.ZipFile, inner: str, dest: str, skip=()) -> int:
    """Copy `<top>/<inner>/...` from the ZIP over `dest`. Returns the number of files written."""
    top = zf.namelist()[0].split("/")[0]
    prefix = f"{top}/{inner}/" if inner else f"{top}/"
    written = 0
    for member in zf.infolist():
        if member.is_dir() or not member.filename.startswith(prefix):
            continue
        rel = member.filename[len(prefix):]
        if not rel or any(rel == s or rel.startswith(s + "/") for s in skip):
            continue
        target = os.path.normpath(os.path.join(dest, rel))
        if not target.startswith(os.path.normpath(dest) + os.sep):
            continue  # never write outside the folder
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with zf.open(member) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)
        written += 1
    return written


def _apply(key: str, repo: str, folder: str, inner: str, skip=()) -> dict:
    clone = _git_root(folder)
    sha = latest_sha(repo, force=True)
    if clone:
        pulled = _git(["pull", "--ff-only", "origin", "main"], clone, timeout=120)
        if not pulled or pulled.returncode != 0:
            detail = (pulled.stderr or pulled.stdout).strip() if pulled else "git is not available"
            raise RuntimeError(f"git pull failed (local changes in the way?): {detail}")
        return {"method": "git", "sha": sha}
    zf = _download_zip(repo)
    written = _overlay(zf, inner, folder, skip)
    if not written:
        raise RuntimeError("The downloaded ZIP did not contain the expected files.")
    state = _load_state()
    state[key] = sha
    _save_state(state)
    return {"method": "zip", "sha": sha, "files": written}


def apply_bridge() -> dict:
    return _apply("bridge", BRIDGE_REPO, ROOT, "", skip=(".git", ".venv", ".env", "__pycache__", "uv.lock"))


def apply_extension(ext_id: str, ext_path: str = "") -> dict:
    folder = resolve_extension_folder(ext_id, ext_path)
    if not folder:
        raise RuntimeError("Could not find the folder Chrome loaded the extension from.")
    if os.path.basename(folder).lower() != EXTENSION_SUBDIR.lower() and not _git_root(folder):
        raise RuntimeError(f"Chrome loaded the extension from '{folder}', which is not the repo's Autono folder.")
    result = _apply("extension", EXTENSION_REPO, folder, EXTENSION_SUBDIR, skip=("node_modules",))
    result["folder"] = folder
    return result
