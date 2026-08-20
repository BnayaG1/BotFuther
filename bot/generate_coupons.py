# -*- coding: utf-8 -*-
"""מחולל קודי קופון — יצירת מחרוזות קודים אקראיות והכנסתן למסד הנתונים."""
from __future__ import annotations

import secrets
import string

from bot.access import insert_coupon_codes

_CODE_ALPHABET = string.ascii_uppercase + string.digits
# להסיר תווים מבלבלים כמו O, 0, I, 1, L
_SAFE_ALPHABET = "".join(c for c in _CODE_ALPHABET if c not in "O0I1L")


def _generate_random_code(length: int = 10) -> str:
    return "".join(secrets.choice(_SAFE_ALPHABET) for _ in range(length))


def generate_coupon_codes(
    *,
    count: int = 1,
    daily_quota: int = 6,
    period_days: int = 30,
    code_length: int = 10,
) -> list[str]:
    """מייצר ומכניס למסד הנתונים רשימת קודי קופון חדשים."""
    codes: list[str] = []
    for _ in range(count):
        code = _generate_random_code(code_length)
        codes.append(code)

    insert_coupon_codes(codes, daily_quota=daily_quota, period_days=period_days)
    return codes
