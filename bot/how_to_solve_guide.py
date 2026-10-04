# -*- coding: utf-8 -*-
"""מצב מדריך לפתרון — מחברת שלב-אחר-שלב (כמו «איך פותרים תרגיל»)."""
from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from typing import Any

from telegram.ext import ContextTypes

from intro.opening import build_how_to_solve_step_keyboard

log = logging.getLogger(__name__)

HOW_TO_SOLVE_COPY_TEXT = (
    "עכשיו כשיש לנו תרגיל, מה שנעשה זה פשוט להעתיק אותו, "
    "כל אחד והדרך שלו למחברת בצורה הבאה:"
)

HOW_TO_SOLVE_STATE_KEYS = (
    "how_to_solve_extracted",
    "how_to_solve_stage",
    "how_to_solve_notebook_message_id",
    "how_to_solve_intro_message_id",
    "how_to_solve_initial_message_id",
    "how_to_solve_moment_intro_message_id",
    "how_to_solve_moment_note_message_id",
    "how_to_solve_nx_points_message_id",
    "how_to_solve_qx_points_message_id",
    "how_to_solve_mx_points_message_id",
)

TrackMessageFn = Callable[[int, Any], None]


def clear_how_to_solve_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in HOW_TO_SOLVE_STATE_KEYS:
        context.chat_data.pop(key, None)


def has_active_how_to_solve(context: ContextTypes.DEFAULT_TYPE) -> bool:
    extracted = context.chat_data.get("how_to_solve_extracted")
    stage = context.chat_data.get("how_to_solve_stage")
    return isinstance(extracted, dict) and isinstance(stage, str)


def init_how_to_solve_state(context: ContextTypes.DEFAULT_TYPE, extracted: dict) -> None:
    clear_how_to_solve_state(context)
    context.chat_data["how_to_solve_extracted"] = copy.deepcopy(extracted)
    context.chat_data["how_to_solve_stage"] = "copy"


async def send_how_to_solve_opening(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    extracted: dict,
    *,
    track_message: TrackMessageFn | None = None,
) -> None:
    """שולח תמונת תרגיל + הודעת «העתקה» עם כפתורי המשך/חזור."""
    from bot.notebook_render import render_notebook_exercise_png_temp

    init_how_to_solve_state(context, extracted)
    initial_path = render_notebook_exercise_png_temp(extracted, cropped=True)
    if initial_path is None:
        raise RuntimeError("initial notebook exercise render returned no image")

    def _track(sent: object | None) -> None:
        if track_message is None or sent is None:
            return
        track_message(chat_id, sent)

    try:
        with initial_path.open("rb") as photo:
            sent_photo = await context.bot.send_photo(chat_id=chat_id, photo=photo)
        _track(sent_photo)
        context.chat_data["how_to_solve_initial_message_id"] = int(
            getattr(sent_photo, "message_id", 0) or 0
        )
        sent_followup = await context.bot.send_message(
            chat_id=chat_id,
            text=HOW_TO_SOLVE_COPY_TEXT,
            reply_markup=build_how_to_solve_step_keyboard(),
        )
        _track(sent_followup)
    finally:
        initial_path.unlink(missing_ok=True)
