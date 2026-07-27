# -*- coding: utf-8 -*-
"""יחידות — טון / kN (1 טון = 10 kN) כמו בדוגמאות הבחינה."""
from __future__ import annotations

TON_TO_KN = 10.0


def ton_to_kn(ton: float) -> float:
    return float(ton) * TON_TO_KN


def kn_to_ton(kn: float) -> float:
    return float(kn) / TON_TO_KN


def format_force_hebrew(ton: float) -> str:
    """שתי שורות: kN ואז טון בסוגריים."""
    kn = ton_to_kn(ton)
    return f"{_fmt(kn)} ק\"נ\n({_fmt(ton)} טון)"


def format_udl_hebrew(ton_per_m: float) -> str:
    kn = ton_to_kn(ton_per_m)
    return f"{_fmt(kn)} ק\"נ למ\"א\n({_fmt(ton_per_m)} טון למ\"א)"


def format_moment_hebrew(ton_m: float) -> str:
    kn = ton_to_kn(ton_m)
    return f"{_fmt(kn)} ק\"נ·מ\n({_fmt(ton_m)} טון·מ)"


def _fmt(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return text
