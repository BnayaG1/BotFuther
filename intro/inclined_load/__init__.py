# -*- coding: utf-8 -*-
"""מבוא — עומס אלכסוני."""
from __future__ import annotations

import math
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_BODY = (
    "בסטטיקה, העיקרון הוא שהכל צריך להיות שווה ל-0 בשביל שהמבנה יהיה יציב.\n"
    "\n"
    "למה אני אומר את זה? כי עומס אנכי או צירי, קל להכניס אותם למשוואה שמתאפסת ל-0. עומס אלכסוני זה כבר לא כזה פשוט, ולכן יותר פשוט לפרק אותו מעומס אלכסוני אחד - לעומס אנכי + צירי. וזה באמת פשוט.\n"
    "\n"
    "קח דוגמא:"
)


def body_hebrew() -> str:
    return _BODY


def build_inclined_load_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("תרגול", callback_data="intro:practice_inclined")],
    ]
    return InlineKeyboardMarkup(rows)


def build_inclined_explanation_text(extracted: dict) -> str:
    """בונה את ההסבר הדינמי המולבש על התרגיל שנשלח."""
    beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
    loads = beam.get("loads") if isinstance(beam.get("loads"), list) else []

    inc_load = next(
        (ld for ld in loads if isinstance(ld, dict) and ld.get("type") == "inclined"),
        None,
    )
    if not inc_load:
        mag = 10.0
        angle = 30.0
        incl_dir = "dr"
    else:
        mag = float(inc_load.get("magnitude_ton", 10.0))
        angle = float(inc_load.get("angle_deg", 30.0))
        incl_dir = str(inc_load.get("incl_dir", "dr"))

    direction_str = "ימינה" if incl_dir == "dr" else "שמאלה"
    mag_str = f"{int(mag)}" if mag.is_integer() else f"{mag:.2f}"
    angle_str = f"{int(angle)}" if angle.is_integer() else f"{angle:.1f}"

    rad = math.radians(angle)
    fy = mag * math.sin(rad)
    fx = mag * math.cos(rad)

    fy_rounded = round(fy, 2)
    fx_rounded = round(fx, 2)

    fy_str = f"{int(fy_rounded)}" if fy_rounded.is_integer() else f"{fy_rounded:g}"
    fx_str = f"{int(fx_rounded)}" if fx_rounded.is_integer() else f"{fx_rounded:g}"

    return (
        "בתרגיל לדוגמא שנשלח עכשיו, יש עומס אלכסוני בודד באמצע הקורה, כל מה שנעשה פה זה נלמד איך לפתוח אותו.\n"
        "\n"
        "כל מה שאנחנו צריכים בשביל לפרק אותו זה את הכיוון שלו, את המשקל והזווית.\n"
        "\n"
        "במקרה שלנו הנתונים הם:\n"
        f"כיוון - {direction_str}\n"
        f"משקל - {mag_str}t\n"
        f"זווית - {angle_str}\n"
        "\n"
        "בשביל למצוא את האנכי הנוסחא היא המשקל כפול sin הזווית.\n"
        "בשביל למצוא את הצירי הנוסחא היא המשקל כפול cos הזווית.\n"
        "\n"
        f"במקרה הזה האנכי יהיה {mag_str}sin({angle_str}).\n"
        f"והצירי יהיה {mag_str}cos({angle_str}).\n"
        "\n"
        f"האנכי יהיה {fy_str}t\n"
        f"הצירי יהיה {fx_str}t\n"
        "\n"
        "ומעכשיו נתייחס לעומס האלכסוני כאילו הוא נראה ככה בתרגיל:"
    )


_PRACTICE_PROMPT = (
    "בוא נראה שהבנת את זה.\n"
    "תשלח לי את הפתרונות כמספרים, עם פסיק באמצע לא משנה הסדר.\n"
    "(לדגומא: 4.87,5.65)"
)


def practice_prompt_hebrew() -> str:
    return _PRACTICE_PROMPT


_TRY_AGAIN_PROMPT = (
    "בוא ננסה שוב.\n"
    "תשלח לי את הפתרונות כמספרים, עם פסיק באמצע לא משנה הסדר.\n"
    "(לדגומא: 4.87,5.65)"
)


def try_again_prompt_hebrew() -> str:
    return _TRY_AGAIN_PROMPT


_INVALID_FORMAT_PROMPT = (
    "בשביל שאצליח להבין את התשובות שרשמת, זה צריך להיראות בנוסח הבא - מספר,מספר.\n"
    "לדוגמא - 4.67,5"
)


def invalid_format_prompt_hebrew() -> str:
    return _INVALID_FORMAT_PROMPT


__all__ = [
    "body_hebrew",
    "build_inclined_explanation_text",
    "build_inclined_load_keyboard",
    "invalid_format_prompt_hebrew",
    "practice_prompt_hebrew",
    "try_again_prompt_hebrew",
]
