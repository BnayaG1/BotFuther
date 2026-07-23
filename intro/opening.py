# -*- coding: utf-8 -*-
"""קובץ פתיחה — הודעת מבוא לסטטיקה + כפתורי נושאים."""
from __future__ import annotations

from collections.abc import Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from intro.ax import body_hebrew as ax_body_hebrew
from intro.equilibrium import body_hebrew as equilibrium_body_hebrew
from intro.load_decomposition import body_hebrew as load_decomposition_body_hebrew

_OPENING_TEXT = (
    "ברוך הבא למבוא! רגע לפני שקופצים לפתור תרגילים, חשוב לי להסביר לך "
    "קודם למה אנחנו עוצרים לרגע על הבסיס.\n"
    "\n"
    "סטטיקה זה קורס שבו הכל מתחבר, וכל נושא מתבסס בדיוק על מה שבא לפניו. "
    "אם רק ננסה לזכור נוסחאות בעל פה בלי להבין למה עושים אותן, אנחנו סתם "
    "נתקעים שעות על כל שאלה ונשארים מתוסכלים מול הדף.\n"
    "\n"
    "ברגע שתתפוס את הראש של הדברים כבר עכשיו, תראה ששאר התרגילים יזרמו לך "
    "הרבה יותר בקלות, ותצליח לפתור הכל לבד בראש שקט לגמרי.\n"
    "\n"
    "לאן תרצה לקחת את זה?"
)

_INTRO_TOPICS: dict[str, tuple[str, Callable[[], str]]] = {
    "load_decomposition": ("פירוק עומסים", load_decomposition_body_hebrew),
    "ax": ("Ax", ax_body_hebrew),
    "equilibrium": ("משוואות שיווי משקל", equilibrium_body_hebrew),
}


def opening_message_hebrew() -> str:
    return _OPENING_TEXT


def build_opening_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(title, callback_data=f"intro:{topic_id}")]
        for topic_id, (title, _) in _INTRO_TOPICS.items()
    ]
    return InlineKeyboardMarkup(rows)


def intro_topic_body_hebrew(topic_id: str) -> str | None:
    entry = _INTRO_TOPICS.get(topic_id)
    if entry is None:
        return None
    return entry[1]()


def parse_intro_callback(data: str) -> str | None:
    """
    intro:<topic_id>
    → topic_id, or None if not an intro callback.
    """
    if not data.startswith("intro:"):
        return None
    topic_id = data.split(":", 1)[-1]
    if topic_id in _INTRO_TOPICS:
        return topic_id
    return None
