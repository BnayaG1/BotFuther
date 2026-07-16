# -*- coding: utf-8 -*-
"""Session תרגיל — זיכרון מקומי מתמונה ועד תמונה הבאה."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

log = logging.getLogger("beam_telegram_bot")

_session_seq = 0


class SolveMode(Enum):
    NOTEBOOK = "notebook"
    ASSISTANT = "assistant"
    ADD_TO_BANK = "add_to_bank"


@dataclass
class SolutionSession:
    session_id: int
    started_at: float = field(default_factory=time.monotonic)
    phase: str = "extracting"  # extracting | draft | solved
    solve_mode: SolveMode = SolveMode.NOTEBOOK
    assistant_beam_kind: str | None = None
    assistant_message_ids: list[int] = field(default_factory=list)
    # snapshot stack for ↩️: restores exact previously sent assistant message
    assistant_prev_stack: list[dict] = field(default_factory=list)
    assistant_last_screen: dict | None = None


@dataclass
class AssistantProgress:
    """מצב עוזר אישי — שלב נוכחי ועומסים לפרוק בשלב 1."""

    beam_kind: str
    extracted: dict
    step_index: int = 0
    sub_index: int = 0
    reaction_sub_index: int = 0
    decomposition_indices: list[int] = field(default_factory=list)


_sessions: dict[int, SolutionSession] = {}
_pending_solve_mode: dict[int, SolveMode] = {}
_assistant_progress: dict[int, AssistantProgress] = {}
_pending_bank_exercise: dict[int, tuple[int, dict]] = {}
# תמונת מקור בהמתנה לאישור «הוספה למאגר» (לפני prepare_image_for_vision).
_pending_bank_submission_image: dict[int, Path] = {}


def _next_session_id() -> int:
    global _session_seq
    _session_seq += 1
    return _session_seq


def has_active_image_session(chat_id: int) -> bool:
    return chat_id in _sessions


def get_solution_session(chat_id: int) -> SolutionSession | None:
    return _sessions.get(chat_id)


def set_pending_solve_mode(chat_id: int, mode: SolveMode) -> None:
    _pending_solve_mode[int(chat_id)] = mode
    log.info("Pending solve mode chat=%s mode=%s", chat_id, mode.value)


def consume_pending_solve_mode(chat_id: int) -> SolveMode | None:
    return _pending_solve_mode.pop(int(chat_id), None)


def set_pending_bank_exercise(chat_id: int, exercise_id: int, extracted: dict) -> None:
    """שומר תרגיל שנשלח מהמאגר וממתין לבחירת מצב פתרון (מחברת/עוזר אישי)."""
    _pending_bank_exercise[int(chat_id)] = (int(exercise_id), extracted)


def consume_pending_bank_exercise(chat_id: int) -> tuple[int, dict] | None:
    return _pending_bank_exercise.pop(int(chat_id), None)


def set_pending_bank_submission_image(chat_id: int, image_path: Path) -> None:
    """שומר נתיב לתמונת מקור עד אישור הוספה למאגר (מחליף עותק קודם אם יש)."""
    clear_pending_bank_submission_image(chat_id)
    _pending_bank_submission_image[int(chat_id)] = Path(image_path)


def peek_pending_bank_submission_image(chat_id: int) -> Path | None:
    path = _pending_bank_submission_image.get(int(chat_id))
    return Path(path) if path is not None else None


def consume_pending_bank_submission_image(chat_id: int) -> Path | None:
    """מחזיר את נתיב התמונה ומסיר מהמילון (בלי למחוק את הקובץ)."""
    path = _pending_bank_submission_image.pop(int(chat_id), None)
    return Path(path) if path is not None else None


def clear_pending_bank_submission_image(chat_id: int) -> None:
    """מוחק עותק זמני של תמונת הוספה למאגר אם קיים."""
    path = _pending_bank_submission_image.pop(int(chat_id), None)
    if path is None:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError as exc:
        log.warning("Failed to delete pending bank image %s: %s", path, exc)


def get_solve_mode(chat_id: int) -> SolveMode:
    session = _sessions.get(int(chat_id))
    if session is not None:
        return session.solve_mode
    return SolveMode.NOTEBOOK


def reset_user_session(chat_id: int) -> None:
    """איפוס מלא — /reset."""
    from bot.vision import clear_vision_context

    clear_vision_context(chat_id)
    _sessions.pop(chat_id, None)
    _pending_solve_mode.pop(chat_id, None)
    _assistant_progress.pop(chat_id, None)
    _pending_bank_exercise.pop(chat_id, None)
    clear_pending_bank_submission_image(chat_id)
    try:
        from personal_assistant.runtime import clear_personal_assistant_progress

        clear_personal_assistant_progress(chat_id)
    except Exception:
        pass
    log.info("User session reset chat=%s", chat_id)


def append_assistant_message_id(chat_id: int, message_id: int) -> None:
    session = _sessions.get(int(chat_id))
    if session is None:
        return
    session.assistant_message_ids.append(int(message_id))


def pop_assistant_message_ids(chat_id: int) -> list[int]:
    session = _sessions.get(int(chat_id))
    if session is None:
        return []
    ids = list(session.assistant_message_ids)
    session.assistant_message_ids.clear()
    return ids


def begin_image_session(chat_id: int, *, solve_mode: SolveMode = SolveMode.NOTEBOOK) -> SolutionSession:
    """תמונה חדשה — מוחק תרגיל קודם, מתחיל session ריק."""
    from bot.vision import clear_vision_context

    clear_vision_context(chat_id)
    _assistant_progress.pop(int(chat_id), None)
    # תמונה חדשה מבטלת הגשה קודמת למאגר שעדיין לא אושרה.
    clear_pending_bank_submission_image(chat_id)
    try:
        from personal_assistant.runtime import clear_personal_assistant_progress

        clear_personal_assistant_progress(chat_id)
    except Exception:
        pass
    session = SolutionSession(
        session_id=_next_session_id(),
        phase="extracting",
        solve_mode=solve_mode,
    )
    _sessions[chat_id] = session
    log.info(
        "New image session chat=%s session_id=%s mode=%s",
        chat_id,
        session.session_id,
        solve_mode.value,
    )
    return session


def push_assistant_prev_state(chat_id: int, *, step_index: int, sub_index: int, reaction_sub_index: int) -> None:
    session = _sessions.get(int(chat_id))
    if session is None:
        return
    session.assistant_prev_stack.append(
        {
            "step_index": int(step_index),
            "sub_index": int(sub_index),
            "reaction_sub_index": int(reaction_sub_index),
        }
    )


def pop_assistant_prev_state(chat_id: int) -> dict | None:
    session = _sessions.get(int(chat_id))
    if session is None or not session.assistant_prev_stack:
        return None
    return session.assistant_prev_stack.pop()


def set_assistant_last_screen(chat_id: int, screen: dict) -> None:
    session = _sessions.get(int(chat_id))
    if session is None:
        return
    session.assistant_last_screen = dict(screen or {})


def get_assistant_last_screen(chat_id: int) -> dict | None:
    session = _sessions.get(int(chat_id))
    if session is None:
        return None
    return session.assistant_last_screen


def has_assistant_prev_state(chat_id: int) -> bool:
    session = _sessions.get(int(chat_id))
    return bool(session and session.assistant_prev_stack)


def clear_assistant_prev_stack(chat_id: int) -> None:
    session = _sessions.get(int(chat_id))
    if session is not None:
        session.assistant_prev_stack.clear()


def mark_session_draft(chat_id: int) -> None:
    session = _sessions.get(chat_id)
    if session is not None:
        session.phase = "draft"


def mark_session_solved(chat_id: int) -> None:
    session = _sessions.get(chat_id)
    if session is not None:
        session.phase = "solved"


def set_assistant_beam_kind(chat_id: int, beam_kind: str | None) -> None:
    session = _sessions.get(int(chat_id))
    if session is not None:
        session.assistant_beam_kind = beam_kind


def get_assistant_beam_kind(chat_id: int) -> str | None:
    session = _sessions.get(int(chat_id))
    if session is None:
        return None
    return session.assistant_beam_kind


def set_assistant_progress(chat_id: int, progress: AssistantProgress) -> None:
    _assistant_progress[int(chat_id)] = progress


def get_assistant_progress(chat_id: int) -> AssistantProgress | None:
    return _assistant_progress.get(int(chat_id))


def has_active_assistant_progress(chat_id: int) -> bool:
    return int(chat_id) in _assistant_progress


def clear_assistant_progress(chat_id: int) -> None:
    _assistant_progress.pop(int(chat_id), None)
