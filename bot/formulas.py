# -*- coding: utf-8 -*-
"""תפריט נוסחאות — בחירת נושא ושליחת תמונה (שלד; תמונות יתווספו בהמשך)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import APP_DIR

FORMULAS_DIR = Path(APP_DIR) / "assets" / "formulas"


@dataclass(frozen=True)
class FormulaTopic:
    topic_id: str
    title: str
    # יחסי ל־FORMULAS_DIR; None = עדיין אין קובץ
    image_relpath: Optional[str] = None

    def image_path(self) -> Optional[Path]:
        if not self.image_relpath:
            return None
        path = FORMULAS_DIR / self.image_relpath
        return path if path.is_file() else None


# נושאים — מתעדכנים כשמתווספים חיתוכי דף הנוסחאות
FORMULA_TOPICS: tuple[FormulaTopic, ...] = (
    FormulaTopic(
        "supports_formulas",
        "נוסחות לתרגילי סמכים",
        "supports_formulas.png",
    ),
    FormulaTopic(
        "cantilever_formulas",
        "נוסחאות לתרגילי ריתום",
        "cantilever_formulas.png",
    ),
    FormulaTopic(
        "load_shapes_q_m",
        "סרטוט הגרפים",
        "load_shapes_q_m.png",
    ),
    FormulaTopic(
        "area_formulas",
        "נוסחאות לחישוב שטחים",
        "area_formulas.png",
    ),
    FormulaTopic(
        "vectors",
        "וקטורים\\אלכסוניים",
        "vectors.png",
    ),
    FormulaTopic(
        "nm_diagram_notes",
        "הערות ודגשים חשובים",
        "nm_diagram_notes.png",
    ),
)

_TOPICS_BY_ID: dict[str, FormulaTopic] = {t.topic_id: t for t in FORMULA_TOPICS}


def get_topic(topic_id: str) -> FormulaTopic | None:
    return _TOPICS_BY_ID.get(topic_id)


def formulas_menu_intro_hebrew() -> str:
    return (
        "📐 *נוסחאות*\n\n"
        "בחר/י נושא — ואשלח את דף הנוסחאות הרלוונטי."
    )


def build_formulas_menu_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for topic in FORMULA_TOPICS:
        rows.append(
            [
                InlineKeyboardButton(
                    topic.title,
                    callback_data=f"formula:topic:{topic.topic_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton("◀️ חזרה לתפריט", callback_data="formula:back")])
    return InlineKeyboardMarkup(rows)


def build_topic_followup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📐 נוסחאות נוספות", callback_data="formula:menu")],
            [InlineKeyboardButton("◀️ חזרה לתפריט", callback_data="formula:back")],
        ]
    )


def parse_formula_callback(data: str) -> tuple[str, str] | None:
    """
    formula:menu
    formula:back
    formula:topic:<id>
    → (action, payload)
    """
    if not data.startswith("formula:"):
        return None
    parts = data.split(":", 2)
    if len(parts) < 2:
        return None
    action = parts[1]
    if action == "topic":
        if len(parts) < 3 or not parts[2]:
            return None
        return "topic", parts[2]
    if action in ("menu", "back"):
        return action, ""
    return None


def topic_pending_caption_hebrew(topic: FormulaTopic) -> str:
    return (
        f"📐 *{topic.title}*\n\n"
        "התמונה לנושא הזה עדיין לא הועלתה.\n"
        "בקרוב — אחרי שיתווסף הקובץ לדף הנוסחאות."
    )


def topic_image_caption_hebrew(topic: FormulaTopic) -> str:
    return f"📐 {topic.title}"


def formulas_locked_reply_hebrew() -> str:
    return (
        "🔒 *נוסחאות זמינות למנויי חבילה בלבד*\n\n"
        "כדי לפתוח את דפי הנוסחאות צריך להפעיל *קוד קופון* "
        "(אחרי רכישת חבילה).\n\n"
        "בלי קופון אפשר לשלוח תמונות תרגיל עם המתנה בין שליחות — "
        "אבל זה לא פותח את ספריית הנוסחאות.\n\n"
        "בחר/י אפשרות למטה:"
    )


def build_formulas_locked_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🛒 רכישת חבילה", callback_data="buy:menu")],
            [InlineKeyboardButton("🎟️ יש לי קוד", callback_data="buy:redeem")],
            [InlineKeyboardButton("◀️ חזרה לתפריט", callback_data="formula:back")],
        ]
    )