"""Local text-to-speech with Piper (https://github.com/OHF-Voice/piper1-gpl).

Nothing heavy is installed with the Bridge. When the user asks for it, Autono has the Bridge:
  1. install the Piper engine (the ``piper-tts`` package) into the Bridge's own folder, never into the
     user's Python, and
  2. download the voices the user picks for their language from the public catalogue
     https://huggingface.co/rhasspy/piper-voices.
Piper is licensed GPL-3.0; it is installed separately at the user's request and not bundled here.
Piper only turns text into speech. It cannot transcribe speech.
"""

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import APP_DIR

PIPER_DIR = Path(os.environ.get("ANTIGRAVITY_PIPER_HOME") or (APP_DIR / "piper"))
LIB_DIR = PIPER_DIR / "lib"
VOICES_DIR = PIPER_DIR / "voices"
CATALOG_FILE = PIPER_DIR / "voices.json"
CATALOG_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json"
FILES_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
CATALOG_MAX_AGE = 7 * 24 * 3600
MAX_TEXT_CHARS = 6000

VOICE_KEY_RE = re.compile(r"^[a-z]{2,3}_[A-Z]{2}-[A-Za-z0-9_]+-(x_low|low|medium|high)$")

_lock = threading.Lock()
_engine_state: Dict[str, Any] = {"installing": False, "error": ""}
_downloads: Dict[str, Dict[str, Any]] = {}
_loaded: Dict[str, Any] = {}


# ───────────── network (one place, so tests can replace it) ─────────────

def _open_url(url: str, timeout: float = 30):
    request = urllib.request.Request(url, headers={"User-Agent": "AntigravityBridge/1.0"})
    return urllib.request.urlopen(request, timeout=timeout)


# ───────────── engine ─────────────

def engine_installed() -> bool:
    return (LIB_DIR / "piper").is_dir() and (LIB_DIR / "onnxruntime").is_dir()


def _python_exe() -> str:
    exe = Path(sys.executable)
    if exe.name.lower().startswith("pythonw"):
        candidate = exe.with_name("python.exe")  # pip needs a console Python
        if candidate.exists():
            return str(candidate)
    return str(exe)


def _ensure_on_path() -> None:
    # appended, not inserted: the Bridge's own packages must win over the copies pip put next to Piper
    if str(LIB_DIR) not in sys.path:
        sys.path.append(str(LIB_DIR))


def install_engine() -> Dict[str, Any]:
    """Install piper-tts into the Bridge's folder on a worker thread (a few minutes, ~300 MB)."""
    with _lock:
        if _engine_state["installing"]:
            return dict(_engine_state)
        _engine_state.update(installing=True, error="")

    def work() -> None:
        try:
            LIB_DIR.mkdir(parents=True, exist_ok=True)
            extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
            proc = subprocess.run(
                [_python_exe(), "-m", "pip", "install", "--upgrade", "--target", str(LIB_DIR), "piper-tts"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900, **extra,
            )
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
                raise RuntimeError(" ".join(tail) or f"pip exited with {proc.returncode}")
            _loaded.clear()
        except Exception as exc:
            _engine_state["error"] = str(exc)[:400]
        finally:
            _engine_state["installing"] = False

    threading.Thread(target=work, daemon=True, name="piper-install").start()
    return dict(_engine_state)


# ───────────── catalogue ─────────────

def _catalog() -> Dict[str, Any]:
    fresh = CATALOG_FILE.exists() and time.time() - CATALOG_FILE.stat().st_mtime < CATALOG_MAX_AGE
    if not fresh:
        try:
            with _open_url(CATALOG_URL, timeout=30) as resp:
                data = resp.read()
            json.loads(data)  # only keep it if it is valid
            PIPER_DIR.mkdir(parents=True, exist_ok=True)
            CATALOG_FILE.write_bytes(data)
        except Exception:
            if not CATALOG_FILE.exists():
                raise
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))


def voice_installed(key: str) -> bool:
    return (VOICES_DIR / f"{key}.onnx").exists() and (VOICES_DIR / f"{key}.onnx.json").exists()


def list_voices(lang: Optional[str] = None) -> List[Dict[str, Any]]:
    """Voices of the catalogue, optionally only one language family ("es" gives es_ES, es_MX, es_AR...)."""
    wanted = (lang or "").lower().replace("-", "_").split("_")[0]
    out = []
    for key, v in _catalog().items():
        language = v.get("language", {})
        if wanted and language.get("family", "").lower() != wanted:
            continue
        onnx = next((f for f in v.get("files", {}) if f.endswith(".onnx")), None)
        size = v["files"][onnx]["size_bytes"] if onnx else 0
        out.append({
            "key": key,
            "name": v.get("name", key),
            "language": language.get("code", ""),
            "language_name": language.get("name_native") or language.get("name_english", ""),
            "country": language.get("country_english", ""),
            "quality": v.get("quality", ""),
            "speakers": v.get("num_speakers", 1),
            "size_mb": round(size / 1e6, 1),
            "installed": voice_installed(key),
        })
    order = {"high": 0, "medium": 1, "low": 2, "x_low": 3}
    out.sort(key=lambda x: (x["language"], order.get(x["quality"], 9), x["name"]))
    return out


# ───────────── voices ─────────────

def download_voice(key: str) -> Dict[str, Any]:
    """Download a voice (model + config) on a worker thread; progress is reported by status()."""
    if not VOICE_KEY_RE.match(key or ""):
        raise ValueError("Invalid voice name")
    entry = _catalog().get(key)
    if not entry:
        raise KeyError(f"Unknown voice: {key}")
    with _lock:
        state = _downloads.get(key)
        if state and state["state"] == "downloading":
            return dict(state)
        files = {path: info for path, info in entry["files"].items() if not path.endswith("MODEL_CARD")}
        total = sum(info["size_bytes"] for info in files.values())
        _downloads[key] = {"state": "downloading", "done": 0, "total": total, "error": ""}

    def work() -> None:
        try:
            VOICES_DIR.mkdir(parents=True, exist_ok=True)
            for path, info in files.items():
                target = VOICES_DIR / Path(path).name
                part = target.with_suffix(target.suffix + ".part")
                md5 = hashlib.md5()
                with _open_url(FILES_BASE + path, timeout=60) as resp, open(part, "wb") as fh:
                    while True:
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        fh.write(chunk)
                        md5.update(chunk)
                        _downloads[key]["done"] += len(chunk)
                if info.get("md5_digest") and md5.hexdigest() != info["md5_digest"]:
                    part.unlink(missing_ok=True)
                    raise RuntimeError(f"Checksum mismatch for {target.name}")
                os.replace(part, target)
            _downloads[key]["state"] = "done"
        except Exception as exc:
            _downloads[key].update(state="error", error=str(exc)[:300])

    threading.Thread(target=work, daemon=True, name=f"piper-voice-{key}").start()
    return dict(_downloads[key])


def delete_voice(key: str) -> bool:
    if not VOICE_KEY_RE.match(key or ""):
        raise ValueError("Invalid voice name")
    _loaded.pop(key, None)
    removed = False
    for suffix in (".onnx", ".onnx.json"):
        p = VOICES_DIR / f"{key}{suffix}"
        if p.exists():
            p.unlink()
            removed = True
    _downloads.pop(key, None)
    return removed


def status() -> Dict[str, Any]:
    installed = sorted(p.name[:-5] for p in VOICES_DIR.glob("*.onnx")) if VOICES_DIR.exists() else []
    return {
        "engine_installed": engine_installed(),
        "engine_installing": _engine_state["installing"],
        "engine_error": _engine_state["error"],
        "voices_installed": installed,
        "downloads": {k: dict(v) for k, v in _downloads.items()},
    }


# ───────────── speaking ─────────────

def _load_voice(key: str):
    """Load (and keep) a voice. Replaced in tests."""
    voice = _loaded.get(key)
    if voice is None:
        _ensure_on_path()
        from piper import PiperVoice  # imported late: it is only there once the engine is installed

        voice = PiperVoice.load(VOICES_DIR / f"{key}.onnx", config_path=VOICES_DIR / f"{key}.onnx.json")
        _loaded[key] = voice
    return voice


def synthesize(text: str, key: str, speed: float = 1.0) -> bytes:
    """Return a WAV file with ``text`` spoken by the voice ``key``."""
    if not VOICE_KEY_RE.match(key or ""):
        raise ValueError("Invalid voice name")
    if not engine_installed():
        raise RuntimeError("The Piper engine is not installed yet")
    if not voice_installed(key):
        raise FileNotFoundError(f"The voice {key} is not downloaded yet")
    text = (text or "").strip()[:MAX_TEXT_CHARS]
    if not text:
        raise ValueError("Nothing to say")
    voice = _load_voice(key)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        syn_config = None
        if speed and abs(speed - 1.0) > 0.01:
            _ensure_on_path()
            from piper.config import SynthesisConfig

            syn_config = SynthesisConfig(length_scale=1.0 / max(0.5, min(2.0, speed)))
        voice.synthesize_wav(text, wav, syn_config)
    return buffer.getvalue()
