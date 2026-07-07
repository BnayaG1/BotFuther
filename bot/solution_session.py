# -*- coding: utf-8 -*-
"""Session תרגיל — זיכרון מקומי מתמונה ועד תמונה הבאה."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger("beam_telegram_bot")

_session_seq = 0


@dataclass
class SolutionSession:
    session_id: int
    started_at: float = field(default_factory=time.monotonic)
    phase: str = "extracting"  # extracting | draft | solved


_sessions: dict[int, SolutionSession] = {}


def _next_session_id() -> int:
    global _session_seq
    _session_seq += 1
    return _session_seq


def has_active_image_session(chat_id: int) -> bool:
    return chat_id in _sessions


def get_solution_session(chat_id: int) -> SolutionSession | None:
    return _sessions.get(chat_id)


def reset_user_session(chat_id: int) -> None:
    """איפוס מלא — /reset."""
    from bot.vision import clear_vision_context

    clear_vision_context(chat_id)
    _sessions.pop(chat_id, None)
    log.info("User session reset chat=%s", chat_id)


def begin_image_session(chat_id: int) -> SolutionSession:
    """תמונה חדשה — מוחק תרגיל קודם, מתחיל session ריק."""
    from bot.vision import clear_vision_context

    clear_vision_context(chat_id)
    session = SolutionSession(session_id=_next_session_id(), phase="extracting")
    _sessions[chat_id] = session
    log.info(
        "New image session chat=%s session_id=%s",
        chat_id,
        session.session_id,
    )
    return session


def mark_session_draft(chat_id: int) -> None:
    session = _sessions.get(chat_id)
    if session is not None:
        session.phase = "draft"


def mark_session_solved(chat_id: int) -> None:
    session = _sessions.get(chat_id)
    if session is not None:
        session.phase = "solved"
