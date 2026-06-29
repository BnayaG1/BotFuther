# -*- coding: utf-8 -*-
"""טעינת .env, קריאת משתני סביבה, ומודל Gemini."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from bot.config import (
    APP_DIR,
    DEFAULT_MODEL,
    DEPRECATED_MODEL_PREFIXES,
    GEMINI_KEY_NAMES,
    TELEGRAM_KEY_NAMES,
)

log = logging.getLogger("beam_telegram_bot")


def load_env_files() -> list[Path]:
    """Load .env from project folder, cwd, or Desktop (parent)."""
    loaded: list[Path] = []
    candidates = [
        APP_DIR / ".env",
        Path.cwd() / ".env",
        APP_DIR.parent / ".env",
    ]
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            load_dotenv(resolved, override=True)
            loaded.append(resolved)
    if not loaded:
        load_dotenv()
    return loaded


def env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def require_env(*names: str, label: str) -> str:
    value = env(*names)
    if not value:
        joined = " / ".join(names)
        log.error("Missing %s — set one of: %s in .env", label, joined)
        log.error(
            "Create file: %s  (see .env.example)",
            APP_DIR / ".env",
        )
        raise SystemExit(1)
    return value


def normalize_model_id(model: str) -> str:
    name = model.strip()
    if name.startswith("models/"):
        name = name[len("models/") :]
    if name.startswith("google/"):
        name = name[len("google/") :]
    return name


def resolve_primary_model() -> str:
    """מודל ראשי מ-.env או ברירת מחדל; מפנה ממודלי 1.5 שהוסרו."""
    raw = normalize_model_id(env("GEMINI_MODEL") or DEFAULT_MODEL)
    if raw.startswith(DEPRECATED_MODEL_PREFIXES):
        log.warning(
            "Model %s is no longer available on Gemini API — using %s instead",
            raw,
            DEFAULT_MODEL,
        )
        return DEFAULT_MODEL
    return raw


def resolve_chat_model() -> str:
    """מודל לצ'אט טקסט — lite לתגובה מהירה."""
    explicit = env("CHAT_MODEL", "GEMINI_CHAT_MODEL")
    if explicit:
        return normalize_model_id(explicit)
    primary = resolve_primary_model()
    if "lite" not in primary.lower():
        return normalize_model_id("gemini-2.5-flash-lite")
    return primary


def resolve_vision_model() -> str:
    """מודל לחילוץ תמונות — איכות גבוהה יותר מצ'אט כשמוגדר lite."""
    explicit = env("VISION_MODEL", "GEMINI_VISION_MODEL")
    if explicit:
        return normalize_model_id(explicit)
    primary = resolve_primary_model()
    if "lite" in primary.lower():
        from bot.config import VISION_QUALITY_MODEL

        return normalize_model_id(VISION_QUALITY_MODEL)
    return primary


def log_startup_config(env_files: list[Path]) -> None:
    if env_files:
        for path in env_files:
            log.info("Loaded .env: %s", path)
    else:
        log.warning("No .env file found — using environment variables only")
        log.warning("Expected file: %s", APP_DIR / ".env")

    tg = env(*TELEGRAM_KEY_NAMES)
    gm = env(*GEMINI_KEY_NAMES)
    log.info("Telegram token: %s", "OK (" + mask_secret(tg) + ")" if tg else "MISSING")
    log.info("Gemini API key: %s", "OK (" + mask_secret(gm) + ")" if gm else "MISSING")
    log.info("Gemini model: %s", resolve_primary_model())
    log.info("Chat model: %s", resolve_chat_model())
    log.info("Vision model: %s", resolve_vision_model())
