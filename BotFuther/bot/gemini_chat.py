# -*- coding: utf-8 -*-
"""Gemini client — חילוץ תמונות בלבד."""
from __future__ import annotations

import logging
import random
import time

from google import genai
from google.genai import types
from google.genai.errors import APIError

from bot.config import (
    CHAT_HTTP_TIMEOUT_MS,
    DEFAULT_MODEL,
    FALLBACK_MODELS,
    GEMINI_HTTP_TIMEOUT_MS,
    GEMINI_KEY_NAMES,
    MAX_RETRIES_PER_MODEL,
    RETRYABLE_API_CODES,
    RETRY_BASE_DELAY_SEC,
)
from bot.env import normalize_model_id, require_env, resolve_primary_model

log = logging.getLogger("beam_telegram_bot")

_gemini_client: genai.Client | None = None
_gemini_model: str | None = None
_chat_client: genai.Client | None = None


def create_gemini_client(*, timeout_ms: int | None = None) -> genai.Client:
    api_key = require_env(*GEMINI_KEY_NAMES, label="Gemini API key")
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            api_version="v1beta",
            timeout=timeout_ms if timeout_ms is not None else GEMINI_HTTP_TIMEOUT_MS,
        ),
    )


def invalidate_gemini_config_cache() -> None:
    """תאימות — auto_validator / system_prompt reload."""
    pass


def gemini_runtime() -> tuple[genai.Client, str]:
    global _gemini_client, _gemini_model
    if _gemini_client is None:
        _gemini_client = create_gemini_client()
        _gemini_model = resolve_primary_model()
    return _gemini_client, _gemini_model or DEFAULT_MODEL


def gemini_chat_client() -> genai.Client:
    """לקוח Gemini לצ'אט — timeout קצר, בלי retry ארוך."""
    global _chat_client
    if _chat_client is None:
        _chat_client = create_gemini_client(timeout_ms=CHAT_HTTP_TIMEOUT_MS)
    return _chat_client


def generate_content_once(
    client: genai.Client,
    *,
    model: str,
    contents,
    config: types.GenerateContentConfig,
):
    """קריאה בודדת — בלי retry ובלי מודל גיבוי."""
    return client.models.generate_content(
        model=normalize_model_id(model),
        contents=contents,
        config=config,
    )


def _model_attempt_order(
    primary: str,
    fallback_models: tuple[str, ...] = FALLBACK_MODELS,
) -> list[str]:
    ordered: list[str] = []
    for name in (primary, *fallback_models):
        norm = normalize_model_id(name)
        if norm and norm not in ordered:
            ordered.append(norm)
    return ordered


def generate_content_with_retries(
    client: genai.Client,
    *,
    model: str,
    contents,
    config: types.GenerateContentConfig,
    fallback_models: tuple[str, ...] = FALLBACK_MODELS,
    max_retries_per_model: int = MAX_RETRIES_PER_MODEL,
    base_delay_sec: float = RETRY_BASE_DELAY_SEC,
):
    """קריאת generateContent עם backoff ומעבר אוטומטי למודל גיבוי על 429/503."""
    last_error: APIError | None = None
    models = _model_attempt_order(model, fallback_models)

    for model_idx, current_model in enumerate(models):
        for attempt in range(max(1, max_retries_per_model)):
            try:
                return client.models.generate_content(
                    model=current_model,
                    contents=contents,
                    config=config,
                )
            except APIError as exc:
                last_error = exc
                if exc.code not in RETRYABLE_API_CODES:
                    raise
                remaining_model_attempts = max_retries_per_model - attempt - 1
                has_next_model = model_idx < len(models) - 1
                if remaining_model_attempts > 0:
                    delay = base_delay_sec * (2**attempt) + random.uniform(0, 0.4)
                    log.warning(
                        "Gemini %s on %s — retry %s/%s in %.1fs",
                        exc.code,
                        current_model,
                        attempt + 2,
                        max_retries_per_model,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                if has_next_model:
                    delay = base_delay_sec * (model_idx + 1)
                    log.warning(
                        "Gemini %s on %s — switching to %s in %.1fs",
                        exc.code,
                        current_model,
                        models[model_idx + 1],
                        delay,
                    )
                    time.sleep(delay)
                    break
                raise
    if last_error is not None:
        raise last_error
    raise RuntimeError("generate_content failed with no API error")


def friendly_gemini_error(exc: Exception, *, casual: bool = False) -> str:
    msg = str(exc).strip()
    if msg.startswith("לא הצלחתי לענות"):
        return msg
    if isinstance(exc, APIError):
        if exc.code in (429, 503):
            return "לא הצלחתי לענות עכשיו — נסה שוב בעוד רגע."
        if exc.code == 400 and "API key not valid" in str(exc):
            return (
                "מפתח Gemini ב-.env לא תקין.\n"
                "עדכן GEMINI_API_KEY מ-Google AI Studio והפעל מחדש את הבוט."
            )
    return f"שגיאה בקריאה ל-Gemini:\n{exc}"
