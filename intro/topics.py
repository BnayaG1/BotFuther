# -*- coding: utf-8 -*-
"""קטלוג נושאי מבוא לסטטיקה + מקלדות Telegram."""
from __future__ import annotations

from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


@dataclass(frozen=True)
class IntroTopic:
    topic_id: str
    title: str
    body_hebrew: str


INTRO_TOPICS: tuple[IntroTopic, ...] = (
    IntroTopic(
        "what_is_statics",
        "מהי סטטיקה?",
        (
            "📚 *מהי סטטיקה?*\n\n"
            "סטטיקה היא ענף במכניקה שעוסק בגופים *במנוחה* — "
            "כלומר כוחות ומומנטים שפועלים על מבנה בלי שהוא זז.\n\n"
            "בקורס שלנו נתמקד בעיקר בקורות: איך מזהים עומסים, "
            "איך מוצאים ריאקציות בסמכים, ואיך בונים דיאגרמות כוח ומומנט.\n\n"
            "הרעיון המרכזי: אם הגוף לא זז — סכום הכוחות וסכום המומנטים חייבים להתאזן."
        ),
    ),
    IntroTopic(
        "forces_vectors",
        "כוחות ווקטורים",
        (
            "➡️ *כוחות ווקטורים*\n\n"
            "כוח הוא וקטור: יש לו *גודל*, *כיוון* ו*נקודת פעולה*.\n\n"
            "בסרטוט מקובל:\n"
            "• חץ למטה / למעלה — כוח אנכי\n"
            "• חץ ימינה / שמאלה — כוח אופקי\n"
            "• כוח אלכסוני — מפרקים לרכיבים Fx ו־Fy\n\n"
            "כשמפרקים אלכסוני, עובדים עם הרכיבים בנפרד במשוואות שיווי המשקל."
        ),
    ),
    IntroTopic(
        "equilibrium",
        "שיווי משקל",
        (
            "⚖️ *שיווי משקל*\n\n"
            "גוף במנוחה מקיים את משוואות שיווי המשקל:\n\n"
            "• ΣFx = 0 — סכום הכוחות האופקיים\n"
            "• ΣFy = 0 — סכום הכוחות האנכיים\n"
            "• ΣM = 0 — סכום המומנטים סביב נקודה\n\n"
            "אלה שלושת הכלים הבסיסיים לפתרון ריאקציות בקורה."
        ),
    ),
    IntroTopic(
        "moments",
        "מומנטים",
        (
            "🔄 *מומנטים*\n\n"
            "מומנט מתאר נטייה של כוח *לסובב* את הגוף סביב נקודה.\n\n"
            "בצורה פשוטה:\n"
            "M = F × d\n"
            "כאשר d הוא הזרוע — המרחק הניצב מקו הכוח עד נקודת הסיבוב.\n\n"
            "סימן המומנט (עם / נגד כיוון השעון) חייב להיות עקבי לכל אורך הפתרון."
        ),
    ),
    IntroTopic(
        "supports_reactions",
        "סמכים וריאקציות",
        (
            "🧱 *סמכים וריאקציות*\n\n"
            "סמך מגביל תזוזה/סיבוב — ולכן נוצרת *ריאקציה* מהמבנה:\n\n"
            "• סמך פשוט (pin) — יכול לתת Ax ו־Ay\n"
            "• גלגלת (roller) — בדרך כלל כוח ניצב למשטח\n"
            "• ריתום (fixed) — כוחות + מומנט קבוע\n\n"
            "מציאת הריאקציות היא לרוב השלב הראשון בפתרון תרגיל קורה."
        ),
    ),
)

_TOPICS_BY_ID: dict[str, IntroTopic] = {t.topic_id: t for t in INTRO_TOPICS}


def get_intro_topic(topic_id: str) -> IntroTopic | None:
    return _TOPICS_BY_ID.get(topic_id)


def intro_menu_intro_hebrew() -> str:
    return (
        "📖 *מבוא לסטטיקה*\n\n"
        "כאן תמצא/י רקע והסברים כלליים — בלי פתרון תרגיל ספציפי.\n"
        "בחר/י נושא:"
    )


def intro_topic_body_hebrew(topic: IntroTopic) -> str:
    return topic.body_hebrew


def build_intro_menu_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for topic in INTRO_TOPICS:
        rows.append(
            [
                InlineKeyboardButton(
                    topic.title,
                    callback_data=f"intro:topic:{topic.topic_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton("◀️ חזרה לתפריט", callback_data="intro:back")])
    return InlineKeyboardMarkup(rows)


def build_intro_topic_followup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📖 נושאים נוספים", callback_data="intro:menu")],
            [InlineKeyboardButton("◀️ חזרה לתפריט", callback_data="intro:back")],
        ]
    )


def parse_intro_callback(data: str) -> tuple[str, str] | None:
    """
    intro:menu
    intro:back
    intro:topic:<id>
    → (action, payload)
    """
    if not data.startswith("intro:"):
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
