"""Local speech-to-text with NVIDIA Parakeet TDT 0.6B v3 (English, Spanish and 23 more European languages).

Nothing heavy is installed with the Bridge. When the user asks for it, Autono has the Bridge:
  1. install the ``onnx-asr`` package (MIT, runs ONNX models on the CPU) into the Bridge's own folder, never
     into the user's Python, and
  2. download the int8 model (about 670 MB, CC-BY-4.0, https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx,
     an ONNX export of https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3).
The model detects English or Spanish by itself, so there is no language to pass.
"""

import io
import os
import subprocess
import sys
import threading
import time
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, Optional

from core.config import APP_DIR

STT_DIR = Path(os.environ.get("ANTIGRAVITY_STT_HOME") or (APP_DIR / "stt"))
LIB_DIR = STT_DIR / "lib"
MODEL_DIR = STT_DIR / "parakeet-tdt-0.6b-v3-int8"
MODEL_NAME = "nemo-parakeet-tdt-0.6b-v3"
BASE_URL = "https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/"
# (file name, expected size in bytes; 0 = do not check)
MODEL_FILES = [
    ("config.json", 0),
    ("vocab.txt", 0),
    ("nemo128.onnx", 0),
    ("decoder_joint-model.int8.onnx", 18_202_004),
    ("encoder-model.int8.onnx", 652_183_999),
]
SAMPLE_RATE = 16000
MAX_SECONDS = 40

_lock = threading.Lock()
_engine_state: Dict[str, Any] = {"installing": False, "error": ""}
_download: Dict[str, Any] = {"state": "idle", "done": 0, "total": 0, "error": ""}
_loaded: Dict[str, Any] = {}
_transcribe_lock = threading.Lock()


def _open_url(url: str, timeout: float = 60):
    request = urllib.request.Request(url, headers={"User-Agent": "AntigravityBridge/1.0"})
    return urllib.request.urlopen(request, timeout=timeout)


# ───────────── engine ─────────────

def engine_installed() -> bool:
    return (LIB_DIR / "onnx_asr").is_dir() and (LIB_DIR / "onnxruntime").is_dir()


def _python_exe() -> str:
    exe = Path(sys.executable)
    if exe.name.lower().startswith("pythonw"):
        candidate = exe.with_name("python.exe")  # pip needs a console Python
        if candidate.exists():
            return str(candidate)
    return str(exe)


def _ensure_on_path() -> None:
    # appended, not inserted: the Bridge's own packages must win over the copies pip put next to onnx-asr
    if str(LIB_DIR) not in sys.path:
        sys.path.append(str(LIB_DIR))


def install_engine() -> Dict[str, Any]:
    """Install onnx-asr into the Bridge's folder on a worker thread (a minute or two, ~150 MB)."""
    with _lock:
        if _engine_state["installing"]:
            return dict(_engine_state)
        _engine_state.update(installing=True, error="")

    def work() -> None:
        try:
            LIB_DIR.mkdir(parents=True, exist_ok=True)
            extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
            proc = subprocess.run(
                [_python_exe(), "-m", "pip", "install", "--upgrade", "--target", str(LIB_DIR), "onnx-asr[cpu,hub]"],
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

    threading.Thread(target=work, daemon=True, name="stt-install").start()
    return dict(_engine_state)


# ───────────── model ─────────────

def model_installed() -> bool:
    return all((MODEL_DIR / name).exists() for name, _ in MODEL_FILES)


def download_model() -> Dict[str, Any]:
    """Download the model on a worker thread; progress is reported by status()."""
    with _lock:
        if _download["state"] == "downloading":
            return dict(_download)
        _download.update(state="downloading", done=0, total=sum(size for _, size in MODEL_FILES) or 1, error="")

    def work() -> None:
        try:
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            for name, expected in MODEL_FILES:
                target = MODEL_DIR / name
                if target.exists() and (not expected or target.stat().st_size == expected):
                    _download["done"] += expected or target.stat().st_size
                    continue
                part = target.with_suffix(target.suffix + ".part")
                written = 0
                with _open_url(BASE_URL + name, timeout=60) as resp, open(part, "wb") as fh:
                    while True:
                        chunk = resp.read(512 * 1024)
                        if not chunk:
                            break
                        fh.write(chunk)
                        written += len(chunk)
                        _download["done"] += len(chunk)
                if expected and written != expected:
                    part.unlink(missing_ok=True)
                    raise RuntimeError(f"{name} came down incomplete ({written} of {expected} bytes). Try again.")
                os.replace(part, target)
            _download["state"] = "done"
        except Exception as exc:
            _download.update(state="error", error=str(exc)[:300])

    threading.Thread(target=work, daemon=True, name="stt-model").start()
    return dict(_download)


def delete_model() -> bool:
    _loaded.clear()
    removed = False
    if MODEL_DIR.exists():
        for p in MODEL_DIR.iterdir():
            p.unlink(missing_ok=True)
            removed = True
    _download.update(state="idle", done=0, total=0, error="")
    return removed


def status() -> Dict[str, Any]:
    return {
        "engine_installed": engine_installed(),
        "engine_installing": _engine_state["installing"],
        "engine_error": _engine_state["error"],
        "model_installed": model_installed(),
        "model_loaded": "model" in _loaded,
        "download": dict(_download),
        "model_name": "NVIDIA Parakeet TDT 0.6B v3 (int8)",
        "languages": ["en", "es"],
    }


# ───────────── transcribing ─────────────

def _load_model():
    """Load (and keep) the model. Replaced in tests."""
    model = _loaded.get("model")
    if model is None:
        _ensure_on_path()
        import onnx_asr  # imported late: it is only there once the engine is installed

        model = onnx_asr.load_model(MODEL_NAME, str(MODEL_DIR), quantization="int8")
        _loaded["model"] = model
    return model


def wav_to_samples(data: bytes):
    """Decode a 16-bit PCM WAV (any rate, mono or stereo) to float32 mono at 16 kHz."""
    import numpy as np  # the Bridge ships numpy; the engine folder has one too

    with wave.open(io.BytesIO(data), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError("Send 16-bit PCM audio")
    audio = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE:
        target = int(len(audio) * SAMPLE_RATE / rate)
        audio = np.interp(np.linspace(0, len(audio) - 1, target), np.arange(len(audio)), audio).astype(np.float32)
    return audio


def transcribe(wav_bytes: bytes) -> Dict[str, Any]:
    if not engine_installed():
        raise RuntimeError("The speech engine is not installed yet")
    if not model_installed():
        raise FileNotFoundError("The speech model is not downloaded yet")
    _ensure_on_path()
    audio = wav_to_samples(wav_bytes)
    if len(audio) < SAMPLE_RATE * 0.2:
        return {"text": "", "seconds": 0.0}
    audio = audio[: SAMPLE_RATE * MAX_SECONDS]
    started = time.time()
    with _transcribe_lock:  # one at a time: the model is not meant to be shared across threads
        model = _load_model()
        result = model.recognize(audio, sample_rate=SAMPLE_RATE)
    text = result if isinstance(result, str) else getattr(result, "text", str(result))
    return {"text": (text or "").strip(), "seconds": round(time.time() - started, 2), "audio_seconds": round(len(audio) / SAMPLE_RATE, 2)}
