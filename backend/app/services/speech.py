import io
import os
from typing import Any

from groq import AsyncGroq
import litellm

from app.config import get_settings

settings = get_settings()


def _get_groq_client(*, api_key: str | None = None, api_base: str | None = None) -> AsyncGroq:
    key = api_key or settings.stt_api_key or settings.tts_api_key or settings.llm_api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        raise ValueError("Groq API key is not configured (set GROQ_API_KEY, STT_API_KEY, TTS_API_KEY, or LLM_API_KEY)")

    kwargs: dict[str, Any] = {"api_key": key}

    base = api_base or settings.stt_api_base or settings.tts_api_base
    if base:
        base = base.rstrip("/")
        if base.endswith("/openai/v1"):
            base = base[:-10]
        elif base.endswith("/v1"):
            base = base[:-3]
        if base and base != "https://api.groq.com":
            kwargs["base_url"] = base

    return AsyncGroq(**kwargs)


async def transcribe(audio_bytes: bytes, filename: str = "audio.webm", content_type: str = "audio/webm") -> str:
    """Speech-to-text using Groq Whisper (with fallback to LiteLLM for non-Groq setups)."""
    model_name = settings.stt_model.strip()
    is_groq = (
        model_name.startswith("groq/")
        or "whisper" in model_name.lower()
        or (settings.stt_api_key and settings.stt_api_key.startswith("gsk_"))
        or (settings.llm_api_key and settings.llm_api_key.startswith("gsk_"))
    )

    if is_groq:
        client = _get_groq_client(api_key=settings.stt_api_key, api_base=settings.stt_api_base)
        groq_model = model_name.removeprefix("groq/")
        if not groq_model or groq_model == "whisper-1":
            groq_model = "whisper-large-v3-turbo"

        transcription = await client.audio.transcriptions.create(
            file=(filename, audio_bytes, content_type),
            model=groq_model,
            response_format="verbose_json",
        )
        return (getattr(transcription, "text", None) or str(transcription)).strip()

    # LiteLLM fallback
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
    if settings.tts_provider.lower() != "groq":
        raise ValueError(f"Unsupported TTS provider: {settings.tts_provider}")
    return await _groq_tts(text)


async def _groq_tts(text: str) -> tuple[bytes, str]:
    """
    Call Groq TTS (PlayAI engine via Groq official Python SDK).
    Docs: https://console.groq.com/docs/text-speech
    """
    client = _get_groq_client(
        api_key=settings.tts_api_key or settings.llm_api_key,
        api_base=settings.tts_api_base,
    )

    model = settings.tts_model.removeprefix("groq/") or "playai-tts"
    voice = "Fritz-PlayAI"

    response = await client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        response_format="mp3",
    )
    audio_bytes = await response.read()
    content_type = response.headers.get("content-type", "audio/mpeg")
    return audio_bytes, content_type
