import io
import time
import wave

import pytest
from fastapi.testclient import TestClient

from core import stt
from server.app import app

client = TestClient(app)


def _wav(seconds=1.0, rate=16000, channels=1):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x10\x00" * int(seconds * rate) * channels)
    return buf.getvalue()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(stt, "STT_DIR", tmp_path)
    monkeypatch.setattr(stt, "LIB_DIR", tmp_path / "lib")
    monkeypatch.setattr(stt, "MODEL_DIR", tmp_path / "model")
    stt._loaded.clear()
    stt._download.update(state="idle", done=0, total=0, error="")
    return tmp_path


def test_status_when_nothing_is_installed(home):
    s = client.get("/v1/stt/status").json()
    assert s["engine_installed"] is False and s["model_installed"] is False
    assert s["languages"] == ["en", "es"]


def test_transcribe_refuses_until_installed(home):
    r = client.post("/v1/stt/transcribe", content=_wav())
    assert r.status_code == 409


def test_transcribe_rejects_empty_body(home):
    assert client.post("/v1/stt/transcribe", content=b"").status_code == 400


def test_model_download_checks_sizes_and_reports_progress(home, monkeypatch):
    class Fake:
        def __init__(self, data):
            self.buf = io.BytesIO(data)
        def read(self, n):
            return self.buf.read(n)
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(stt, "MODEL_FILES", [("a.txt", 0), ("b.onnx", 5)])
    monkeypatch.setattr(stt, "_open_url", lambda url, timeout=60: Fake(b"12345" if url.endswith("b.onnx") else b"x"))
    client.post("/v1/stt/model/download")
    for _ in range(50):
        if client.get("/v1/stt/status").json()["download"]["state"] != "downloading":
            break
        time.sleep(0.05)
    s = client.get("/v1/stt/status").json()
    assert s["download"]["state"] == "done" and s["model_installed"] is True
    assert client.delete("/v1/stt/model").json()["deleted"] is True
    assert client.get("/v1/stt/status").json()["model_installed"] is False


def test_incomplete_download_is_an_error(home, monkeypatch):
    class Short:
        def read(self, n, _d=[b"123", b""]):
            return _d.pop(0)
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(stt, "MODEL_FILES", [("b.onnx", 5)])
    monkeypatch.setattr(stt, "_open_url", lambda url, timeout=60: Short())
    client.post("/v1/stt/model/download")
    for _ in range(50):
        if client.get("/v1/stt/status").json()["download"]["state"] != "downloading":
            break
        time.sleep(0.05)
    assert client.get("/v1/stt/status").json()["download"]["state"] == "error"


def test_transcribe_uses_the_model(home, monkeypatch):
    pytest.importorskip("numpy")
    (home / "lib" / "onnx_asr").mkdir(parents=True)
    (home / "lib" / "onnxruntime").mkdir()
    monkeypatch.setattr(stt, "MODEL_FILES", [("m.bin", 0)])
    (home / "model").mkdir()
    (home / "model" / "m.bin").write_bytes(b"x")

    class Model:
        def recognize(self, audio, sample_rate=16000):
            assert sample_rate == 16000 and len(audio) == 16000
            return " hola mundo "

    monkeypatch.setattr(stt, "_load_model", lambda: Model())
    r = client.post("/v1/stt/transcribe", content=_wav(1.0, rate=16000))
    assert r.status_code == 200 and r.json()["text"] == "hola mundo"
    # other sample rates and stereo are brought to 16 kHz mono
    r = client.post("/v1/stt/transcribe", content=_wav(1.0, rate=48000, channels=2))
    assert r.status_code == 200
