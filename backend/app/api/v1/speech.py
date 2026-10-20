from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.api.deps import require_api_key
from app.services import speech as speech_service

router = APIRouter(prefix="/speech", tags=["speech"], dependencies=[Depends(require_api_key)])


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
) -> dict[str, str]:
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty audio")
    try:
        text = await speech_service.transcribe(
            data,
            filename=file.filename or "audio.webm",
            content_type=file.content_type or "audio/webm",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Transcription failed: {exc}") from exc
    return {"text": text}


@router.post("/speak")
async def speak(text: str = Form(...)) -> Response:
    if not text.strip():
        raise HTTPException(400, "Empty text")
    try:
        audio, content_type = await speech_service.speak(text.strip())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"TTS failed: {exc}") from exc
    return Response(content=audio, media_type=content_type)
