import json
from typing import Any

import litellm

from app.config import get_settings

settings = get_settings()


def _chat_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "api_key": settings.llm_api_key or None,
    }
    if settings.llm_api_base:
        kwargs["api_base"] = settings.llm_api_base
    return kwargs


def _embed_kwargs() -> dict[str, Any]:
    key = settings.embedding_api_key or settings.llm_api_key
    kwargs: dict[str, Any] = {
        "model": settings.embedding_model,
        "api_key": key or None,
    }
    base = settings.embedding_api_base or settings.llm_api_base
    if base:
        kwargs["api_base"] = base
    return kwargs


async def chat(messages: list[dict[str, str]], *, temperature: float = 0.2, response_format: dict | None = None) -> str:
    kwargs = _chat_kwargs()
    if response_format:
        kwargs["response_format"] = response_format
    response = await litellm.acompletion(messages=messages, temperature=temperature, **kwargs)
    return response.choices[0].message.content or ""


async def chat_json(messages: list[dict[str, str]], *, temperature: float = 0.1) -> dict[str, Any]:
    raw = await chat(
        messages,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    # Strip markdown fences if a local model ignores response_format
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if lines else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    kwargs = _embed_kwargs()
    response = await litellm.aembedding(input=texts, **kwargs)
    # litellm returns data sorted by index
    data = sorted(response.data, key=lambda d: d["index"])
    return [d["embedding"] for d in data]


async def embed_one(text: str) -> list[float]:
    vectors = await embed_texts([text])
    return vectors[0]
