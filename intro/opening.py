# -*- coding: utf-8 -*-
"""קובץ פתיחה — הודעת מבוא לסטטיקה + כפתור המשך."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_OPENING_TEXT = (
    "סטטיקה זה בסך הכל קורס שבודק איך קורה או בניין נשארים במקום ולא זזים.\n"
    "\n"
    "החוק היחיד פה זה שהכל חייב להתאפס.\n"
    "\n"
    "אם יש משקל שדוחף למטה, החיבורים של הקורה לאדמה או לקיר חייבים להחזיר "
    "בדיוק אותו כוח למעלה כדי לאזן אותו. אם משהו מנסה לסובב את המבנה, חייב "
    "להיות כוח שמונע את הסיבוב הזה. אם משהו לא מתאפס – המבנה זז, ובבניין זה "
    "אומר שהוא פשוט קורס.\n"
    "\n"
    "בגדול, בתרגילים יבקשו מכם לחשב בעיקר שלושה דברים:\n"
    "\n"
    "כמה כוח החיבורים (הסמכים) מחזירים כדי שהכל יישאר יציב.\n"
    "\n"
    "איך הכוח עובר בתוך האלמנט (לחיצה, מתיחה, או כוח שמנסה לחתוך את הקורה).\n"
    "\n"
    "איפה הקורה מתכופפת הכי הרבה בגלל העומס (מומנט), שזה האזור הכי מסוכן "
    "שצריך לחזק.\n"
    "\n"
    "לפני שאתם מתחילים לכתוב משוואות, תסתכלו רגע על השרטוט. תבינו לאן "
    "הכוחות רוצים לקחת את המבנה ואיך הוא מחזיק מעמד. ברגע שמבינים את "
    "ההיגיון בראש, הנתונים והמספרים מסתדרים הרבה יותר בקלות.\n"
    "\n"
    "לחץ המשך להסבר על איך בפועל נפתור תרגילים."
)


def opening_message_hebrew() -> str:
    return _OPENING_TEXT


def build_opening_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("המשך", callback_data="intro:continue")]]
    )


def parse_intro_callback(data: str) -> str | None:
    """
    intro:continue
    → action name, or None if not an intro callback.
    """
    if not data.startswith("intro:"):
        return None
    action = data.split(":", 1)[-1]
    if action == "continue":
        return action
    return None
