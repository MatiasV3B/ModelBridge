"""Speech-to-text endpoints (Parakeet): install the engine, download the model, transcribe."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from core import stt

router = APIRouter(tags=["Speech to text"])
logger = logging.getLogger("antigravity_bridge")

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # ~4 minutes of 16 kHz audio; the model itself takes far less


@router.get("/v1/stt/status")
async def stt_status():
    return stt.status()


@router.post("/v1/stt/engine/install")
async def stt_install_engine():
    return stt.install_engine()


@router.post("/v1/stt/model/download")
async def stt_download_model():
    return stt.download_model()


@router.delete("/v1/stt/model")
async def stt_delete_model():
    return {"deleted": stt.delete_model()}


@router.post("/v1/stt/transcribe")
async def stt_transcribe(request: Request):
    """Body: a 16-bit PCM WAV file. Returns the text (the model detects English or Spanish by itself)."""
    data = await request.body()
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Send a WAV file of up to 8 MB")
    try:
        return await asyncio.to_thread(stt.transcribe, data)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.error(f"Speech recognition failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")
