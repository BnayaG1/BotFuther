# -*- coding: utf-8 -*-
"""שלב פתיחה — שתי הודעות לפני כניסה לפרוק."""

from __future__ import annotations

from personal_assistant.decomposition import decomposition_load_entries
from personal_assistant.reactions import ReactionBeamKind, detect_reaction_beam_kind


def _beam_kind_short_hebrew(kind: ReactionBeamKind) -> str:
    if kind == ReactionBeamKind.CANTILEVER:
        return "ריתום"
    if kind == ReactionBeamKind.SIMPLY_SUPPORTED:
        return "2 סמכים"
    return "קורה"


def build_plan_message_hebrew(extracted: dict) -> str:
    """הודעת פתיחה 1 — הסבר על התרגיל הספציפי."""
    kind = detect_reaction_beam_kind(extracted)
    count = len(decomposition_load_entries(extracted))
    short_kind = _beam_kind_short_hebrew(kind)
    lines = [f"מעולה, מדובר בתרגיל {short_kind}.", ""]
    if count == 0:
        lines.append("בתרגיל הזה אין עומסים מפורסים או אלכסוניים לפרוק.")
    elif count == 1:
        lines.append("במקרה שלנו יש עומס בעייתי אחד שנצטרך לפרק.")
    else:
        lines.append(f"במקרה שלנו יש {count} עומסים בעייתיים שנצטרך לפרק.")
    return "\n".join(lines)


def build_menu_message_hebrew(extracted: dict) -> str:
    """הודעת פתיחה 2 — שאלה איך המשתמש רוצה להמשיך."""
    if len(decomposition_load_entries(extracted)) == 0:
        return "שנמשיך?"
    return "איך תרצה להמשיך?"


def build_opening_messages_hebrew(extracted: dict) -> tuple[str, str]:
    """שתי הודעות הפתיחה בסדר השליחה."""
    return (
        build_plan_message_hebrew(extracted),
        build_menu_message_hebrew(extracted),
    )
