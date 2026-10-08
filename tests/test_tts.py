"""Piper text-to-speech: catalogue by language, voice downloads, speaking (no network, no real engine)."""

import hashlib
import io
import json
import time
import wave

import httpx
import pytest

from core import tts
from server.app import app

ONNX = b"fake-onnx-model" * 1000
CONFIG = json.dumps({"audio": {"sample_rate": 22050}}).encode()


def _catalog():
    def entry(key, family, code, name, quality, native):
        base = f"{family}/{code}/{name}/{quality}/{key}"
        return {
            "key": key, "name": name, "quality": quality, "num_speakers": 1,
            "language": {"code": code, "family": family, "name_native": native, "name_english": native, "country_english": code[-2:]},
            "files": {
                f"{base}.onnx": {"size_bytes": len(ONNX), "md5_digest": hashlib.md5(ONNX).hexdigest()},
                f"{base}.onnx.json": {"size_bytes": len(CONFIG), "md5_digest": hashlib.md5(CONFIG).hexdigest()},
                f"{base}.MODEL_CARD": {"size_bytes": 5, "md5_digest": "x"},
            },
        }
    return {
        "es_ES-ana-medium": entry("es_ES-ana-medium", "es", "es_ES", "ana", "medium", "Español"),
        "es_MX-luis-high": entry("es_MX-luis-high", "es", "es_MX", "luis", "high", "Español"),
        "en_US-sam-low": entry("en_US-sam-low", "en", "en_US", "sam", "low", "English"),
    }


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


@pytest.fixture
def piper_home(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "PIPER_DIR", tmp_path)
    monkeypatch.setattr(tts, "LIB_DIR", tmp_path / "lib")
    monkeypatch.setattr(tts, "VOICES_DIR", tmp_path / "voices")
    monkeypatch.setattr(tts, "CATALOG_FILE", tmp_path / "voices.json")
    tts._downloads.clear()
    tts._loaded.clear()
    catalog = _catalog()

    def fake_open(url, timeout=30):
        if url == tts.CATALOG_URL:
            return _Resp(json.dumps(catalog).encode())
        if url.endswith(".onnx"):
            return _Resp(ONNX)
        if url.endswith(".onnx.json"):
            return _Resp(CONFIG)
        raise AssertionError("unexpected url " + url)

    monkeypatch.setattr(tts, "_open_url", fake_open)
    return tmp_path


def _wait_download(key):
    deadline = time.time() + 5
    while tts._downloads[key]["state"] == "downloading" and time.time() < deadline:
        time.sleep(0.02)
    return tts._downloads[key]


def test_voices_are_listed_by_language_family(piper_home):
    spanish = tts.list_voices("es")
    assert [v["key"] for v in spanish] == ["es_MX-luis-high", "es_ES-ana-medium"] or {v["key"] for v in spanish} == {"es_ES-ana-medium", "es_MX-luis-high"}
    assert all(v["language"].startswith("es_") for v in spanish)
    assert [v["key"] for v in tts.list_voices("en-US")] == ["en_US-sam-low"]
    assert len(tts.list_voices()) == 3
    assert spanish[0]["size_mb"] >= 0 and spanish[0]["installed"] is False


def test_download_verifies_and_installs_a_voice(piper_home):
    state = tts.download_voice("es_ES-ana-medium")
    assert state["state"] == "downloading"
    final = _wait_download("es_ES-ana-medium")
    assert final["state"] == "done" and final["done"] == final["total"]
    assert tts.voice_installed("es_ES-ana-medium")
    assert (piper_home / "voices" / "es_ES-ana-medium.onnx").read_bytes() == ONNX
    assert not list((piper_home / "voices").glob("*.part"))
    assert "es_ES-ana-medium" in tts.status()["voices_installed"]
    assert tts.delete_voice("es_ES-ana-medium") is True
    assert not tts.voice_installed("es_ES-ana-medium")


def test_corrupt_download_is_rejected(piper_home, monkeypatch):
    real = tts._open_url
    monkeypatch.setattr(tts, "_open_url", lambda url, timeout=30: _Resp(b"garbage") if url.endswith(".onnx") else real(url, timeout))
    tts.download_voice("en_US-sam-low")
    final = _wait_download("en_US-sam-low")
    assert final["state"] == "error" and "Checksum" in final["error"]
    assert not tts.voice_installed("en_US-sam-low")


def test_voice_names_cannot_escape_the_folder(piper_home):
    for bad in ("../../etc/passwd", "es_ES-ana-medium/../x", "", "evil"):
        with pytest.raises(ValueError):
            tts.download_voice(bad)
        with pytest.raises(ValueError):
            tts.delete_voice(bad)
    with pytest.raises(KeyError):
        tts.download_voice("es_ES-nobody-high")


class _FakeVoice:
    def synthesize_wav(self, text, wav_file, syn_config=None):
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x01\x00" * 2205)


def _ready(piper_home, monkeypatch):
    (piper_home / "lib" / "piper").mkdir(parents=True)
    (piper_home / "lib" / "onnxruntime").mkdir(parents=True)
    tts.download_voice("es_ES-ana-medium")
    _wait_download("es_ES-ana-medium")
    monkeypatch.setattr(tts, "_load_voice", lambda key: _FakeVoice())


def test_synthesize_returns_a_wav_and_explains_what_is_missing(piper_home, monkeypatch):
    with pytest.raises(RuntimeError):
        tts.synthesize("hola", "es_ES-ana-medium")  # engine not installed
    _ready(piper_home, monkeypatch)
    audio = tts.synthesize("Hola mundo", "es_ES-ana-medium")
    with wave.open(io.BytesIO(audio)) as w:
        assert w.getframerate() == 22050 and w.getnframes() == 2205
    with pytest.raises(FileNotFoundError):
        tts.synthesize("hola", "en_US-sam-low")
    with pytest.raises(ValueError):
        tts.synthesize("   ", "es_ES-ana-medium")


@pytest.mark.anyio
async def test_http_endpoints(piper_home, monkeypatch):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        voices = (await client.get("/v1/tts/voices", params={"lang": "es"})).json()["voices"]
        assert {v["key"] for v in voices} == {"es_ES-ana-medium", "es_MX-luis-high"}

        assert (await client.post("/v1/tts/voices/download", json={"voice": "../x"})).status_code == 400
        assert (await client.post("/v1/tts/voices/download", json={"voice": "es_ES-nobody-high"})).status_code == 404
        assert (await client.post("/v1/tts/speak", json={"text": "hola", "voice": "es_ES-ana-medium"})).status_code == 409

        _ready(piper_home, monkeypatch)
        status = (await client.get("/v1/tts/status")).json()
        assert status["engine_installed"] and "es_ES-ana-medium" in status["voices_installed"]
        spoken = await client.post("/v1/tts/speak", json={"text": "hola", "voice": "es_ES-ana-medium"})
        assert spoken.status_code == 200 and spoken.headers["content-type"] == "audio/wav"
        assert spoken.content[:4] == b"RIFF"
