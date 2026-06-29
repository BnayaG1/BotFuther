# -*- coding: utf-8 -*-
"""לקחי חילוץ מ-learned_extraction_rules.json — ללא שכבת צ'אט."""
from __future__ import annotations

import logging
from pathlib import Path

from bot.config import APP_DIR
from bot.validation_fix_engine import LEARNED_RULES_PATH, _load_rules_data

log = logging.getLogger("beam_telegram_bot")

_rules_mtime: float | None = None


def _rules_file_mtime() -> float | None:
    if not LEARNED_RULES_PATH.is_file():
        return None
    return LEARNED_RULES_PATH.stat().st_mtime


def get_vision_learned_hint() -> str:
    """הנחיות חילוץ מכללים שנלמדו מבדיקות regression."""
    rules = _load_rules_data().get("rules") or []
    if not isinstance(rules, list) or not rules:
        return ""
    lines = ["LEARNED FROM PAST VALIDATION (apply to this extraction):"]
    for rule in rules[:10]:
        if not isinstance(rule, dict):
            continue
        desc = str(rule.get("description", "")).strip()
        if desc:
            lines.append(f"- {desc}")
    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def reload_system_instruction_if_changed() -> bool:
    """מחזיר True אם קובץ הכללים עודכן מאז הטעינה האחרונה."""
    global _rules_mtime
    mtime = _rules_file_mtime()
    if mtime is None:
        return False
    if _rules_mtime is not None and mtime <= _rules_mtime:
        return False
    _rules_mtime = mtime
    from bot.gemini_chat import invalidate_gemini_config_cache

    invalidate_gemini_config_cache()
    log.info("Reloaded learned extraction rules")
    return True


def ensure_system_prompt_file(*, mistakes: list[dict] | None = None) -> Path:
    """תאימות לאחור — אין עוד system_prompt.txt מלא."""
    _ = mistakes
    return APP_DIR / "system_prompt.txt"
