# -*- coding: utf-8 -*-
"""רישום תבניות נתונים + תצורת שרטוט נעולה.

המראה הוויזואלי נקבע רק ב־``exercise_generator/render/`` (קוד נעול אחד).
תבניות כאן מספקות **נתונים** בלבד. ברירת המחדל (כולל אות B בבוט) תמיד
משתמשת ב־``LOCKED_FAMILY`` — בלי בחירה אקראית בין תצורות שונות.
תבניות נוספות נשארות זמינות רק ל־CLI עם ``--family`` לצורך פיתוח.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from exercise_generator.schema import Exercise
from exercise_generator.templates import (
    double_overhang_mixed,
    overhang_stepped_udl,
    rich_combo,
    roller_pin_overhang,
    span_point_stepped_udl,
)

Builder = Callable[..., Exercise]

# תצורת הנתונים הנעולה לכל תרגיל שמופק כברירת מחדל
LOCKED_FAMILY = overhang_stepped_udl.FAMILY_ID

_REGISTRY: dict[str, Builder] = {
    overhang_stepped_udl.FAMILY_ID: overhang_stepped_udl.build_example,
    span_point_stepped_udl.FAMILY_ID: span_point_stepped_udl.build_example,
    roller_pin_overhang.FAMILY_ID: roller_pin_overhang.build_example,
    double_overhang_mixed.FAMILY_ID: double_overhang_mixed.build_example,
    rich_combo.FAMILY_ID: rich_combo.build_example,
}


def list_families() -> list[str]:
    return sorted(_REGISTRY.keys())


def get_builder(family_id: str) -> Builder:
    if family_id not in _REGISTRY:
        known = ", ".join(list_families())
        raise KeyError(f"Unknown family {family_id!r}. Known: {known}")
    return _REGISTRY[family_id]


def pick_family(rng: Any, family: str | None = None) -> str:
    """ברירת מחדל: תמיד LOCKED_FAMILY. ``family`` רק לכפייה מפורשת (CLI)."""
    del rng  # שמור לחתימה עתידית כשיהיו חוקי הגרלת נתונים
    if family is not None:
        if family not in _REGISTRY:
            get_builder(family)  # raise
        return family
    return LOCKED_FAMILY


def build_family(family_id: str, *, seed: int | None = None) -> Exercise:
    return get_builder(family_id)(seed=seed)
