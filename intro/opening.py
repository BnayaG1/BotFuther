# -*- coding: utf-8 -*-
"""קובץ פתיחה — הודעת לימוד בסיס + כפתורי נושאים."""
from __future__ import annotations

from collections.abc import Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from intro.distributed_load import body_hebrew as distributed_load_body_hebrew
from intro.inclined_load import body_hebrew as inclined_load_body_hebrew

_OPENING_TEXT = "לאן תרצה לקחת את זה?"

_INTRO_MAIN_BUTTONS = [
    ("how_to_solve_placeholder", "איך פותרים תרגיל"),
    ("distributed_load", "עומס מפורס"),
    ("inclined_load", "עומס אלכסוני"),
]

_INTRO_TOPIC_BODIES: dict[str, Callable[[], str]] = {
    "distributed_load": distributed_load_body_hebrew,
    "inclined_load": inclined_load_body_hebrew,
}


def opening_message_hebrew() -> str:
    return _OPENING_TEXT


def build_opening_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(title, callback_data=f"intro:{topic_id}")]
        for topic_id, title in _INTRO_MAIN_BUTTONS
    ]
    return InlineKeyboardMarkup(rows)


def build_how_to_solve_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("2 סמכים", callback_data="intro:how_to_solve_supports")],
        [InlineKeyboardButton("ריתום", callback_data="intro:how_to_solve_fixed")],
        [InlineKeyboardButton("חזור", callback_data="intro:main")],
    ])


def build_how_to_solve_step_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("המשך", callback_data="intro:mavo_continue")],
        [InlineKeyboardButton("חזור", callback_data="intro:how_to_solve_back")],
    ])


def build_how_to_solve_finish_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("ראשי", callback_data="menu:statics"),
            InlineKeyboardButton("לתרגול", callback_data="menu:give_exercise"),
        ],
    ])


def intro_topic_body_hebrew(topic_id: str) -> str | None:
    func = _INTRO_TOPIC_BODIES.get(topic_id)
    if func is None:
        return None
    return func()


def parse_intro_callback(data: str) -> str | None:
    """
    intro:<topic_id>
    → topic_id, or None if not an intro callback.
    """
    if not data.startswith("intro:"):
        return None
    topic_id = data.split(":", 1)[-1]
    valid_ids = {
        "how_to_solve_placeholder",
        "how_to_solve_supports",
        "how_to_solve_fixed",
        "how_to_solve_back",
        "main",
        "mavo_continue",
        "practice_inclined",
        "practice_distributed",
        "distributed_on_support",
        "inclined_try_again",
        "inclined_show_solution",
        "distributed_try_again",
        "distributed_show_solution",
        *_INTRO_TOPIC_BODIES.keys(),
    }
    if topic_id in valid_ids:
        return topic_id
    return None
