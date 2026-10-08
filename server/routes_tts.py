"""Text-to-speech endpoints (Piper): install the engine, pick voices by language, speak."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from core import tts

router = APIRouter(tags=["Text to speech"])
logger = logging.getLogger("antigravity_bridge")


class SpeakRequest(BaseModel):
    text: str
    voice: str
    speed: Optional[float] = 1.0


class VoiceRequest(BaseModel):
    voice: str


@router.get("/v1/tts/status")
async def tts_status():
    return tts.status()


@router.get("/v1/tts/voices")
async def tts_voices(lang: Optional[str] = Query(None, description="Language, e.g. 'es' or 'en'")):
    try:
        return {"voices": await asyncio.to_thread(tts.list_voices, lang)}
    except Exception as exc:
        logger.warning(f"Could not load the Piper voice catalogue: {exc}")
        raise HTTPException(status_code=502, detail=f"Could not load the voice catalogue: {exc}")


@router.post("/v1/tts/engine/install")
async def tts_install_engine():
    return tts.install_engine()


@router.post("/v1/tts/voices/download")
async def tts_download_voice(req: VoiceRequest):
    try:
        return await asyncio.to_thread(tts.download_voice, req.voice)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'\""))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not start the download: {exc}")


@router.delete("/v1/tts/voices/{voice}")
async def tts_delete_voice(voice: str):
    try:
        return {"deleted": tts.delete_voice(voice)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/v1/tts/speak")
async def tts_speak(req: SpeakRequest):
    try:
        audio = await asyncio.to_thread(tts.synthesize, req.text, req.voice, req.speed or 1.0)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.error(f"Piper failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Speech failed: {exc}")
    return Response(content=audio, media_type="audio/wav")
