# -*- coding: utf-8 -*-
"""יחידות — טון / kN (1 טון = 10 kN) כמו בדוגמאות הבחינה."""
from __future__ import annotations

TON_TO_KN = 10.0


def ton_to_kn(ton: float) -> float:
    return float(ton) * TON_TO_KN


def kn_to_ton(kn: float) -> float:
    return float(kn) / TON_TO_KN


def format_force_hebrew(ton: float) -> str:
    """מספר + t צמוד (למשל 6t)."""
    return f"{_fmt(ton)}t"


def format_udl_hebrew(ton_per_m: float) -> str:
    """מספר + t/m צמוד (למשל 4t/m)."""
    return f"{_fmt(ton_per_m)}t/m"


def format_moment_hebrew(ton_m: float) -> str:
    """מספר + tm צמוד (למשל 3tm)."""
    return f"{_fmt(ton_m)}tm"


def _fmt(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return text
