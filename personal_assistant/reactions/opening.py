# -*- coding: utf-8 -*-
"""הודעת פתיחה לכניסה לשלב הריאקציות — אחרי סיום הפרוק."""

from __future__ import annotations


def _beam_kind_short_hebrew(kind: str) -> str:
    if kind == "cantilever":
        return "ריתום"
    if kind == "simply_supported":
        return "2 סמכים"
    return "קורה"


def build_reactions_opening_message_hebrew(
    *,
    beam_kind: str,
    had_decomposition: bool,
    has_loads_to_decompose: bool = False,
) -> str:
    """הודעת מעבר לשלב הריאקציות."""
    if had_decomposition:
        short_kind = _beam_kind_short_hebrew(beam_kind)
        lines = [
            "סיימנו את פירוק העומסים!",
            "",
            f"עכשיו נעבור לשלב השני — מציאת הריאקציות ({short_kind}).",
            "נשתמש בעומסים שפירקנו בשלב הקודם.",
            "",
            "לחץ/י כדי להתחיל.",
        ]
        return "\n".join(lines)
    if has_loads_to_decompose:
        return (
            "הגענו לשלב הריאקציות.\n"
            "\n"
            "בחר/י למטה באיזו ריאקציה להתחיל, "
            "או לחץ/י «המשך» כדי להתקדם לפי הסדר."
        )
    return (
        "מכיוון שלא היה עומסים לפרק, אנחנו עוברים לשלב של מציאת הריאקציות.\n"
        "\n"
        "לחץ/י כדי להתחיל."
    )
