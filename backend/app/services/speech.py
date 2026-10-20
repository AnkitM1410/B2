import io
from typing import Any

import httpx
import litellm

from app.config import get_settings

settings = get_settings()


async def transcribe(audio_bytes: bytes, filename: str = "audio.webm", content_type: str = "audio/webm") -> str:
    """Speech-to-text via LiteLLM / OpenAI-compatible Whisper endpoint."""
    key = settings.stt_api_key or settings.llm_api_key
    kwargs: dict[str, Any] = {
        "model": settings.stt_model,
        "file": (filename, io.BytesIO(audio_bytes), content_type),
        "api_key": key or None,
    }
    base = settings.stt_api_base or settings.llm_api_base
    if base:
        kwargs["api_base"] = base
    result = await litellm.atranscription(**kwargs)
    if isinstance(result, dict):
        return (result.get("text") or "").strip()
    return (getattr(result, "text", None) or str(result)).strip()


async def speak(text: str) -> tuple[bytes, str]:
    """Text-to-speech. Returns (audio_bytes, content_type)."""
    if settings.tts_provider.lower() != "grok":
        raise ValueError(f"Unsupported TTS provider: {settings.tts_provider}")
    return await _grok_tts(text)


async def _grok_tts(text: str) -> tuple[bytes, str]:
    """
    Call xAI / Grok TTS.
    Endpoint shape may evolve; override TTS_API_BASE / TTS_MODEL in .env.
    """
    if not settings.tts_api_key:
        raise ValueError("TTS_API_KEY is not set")

    url = settings.tts_api_base.rstrip("/") + "/audio/speech"
    headers = {
        "Authorization": f"Bearer {settings.tts_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.tts_model,
        "input": text,
        "voice": "alloy",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "audio/mpeg")
        return resp.content, content_type
