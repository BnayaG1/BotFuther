# -*- coding: utf-8 -*-
"""חיבור איברי משוואה ופירוק סוגריים לתצוגה בפתרון המחברת."""
from __future__ import annotations

import re

import core.statics_calculator as solver


def _clean_math_signs(text: str) -> str:
    text = re.sub(r"\+\s*-", "- ", text)
    text = re.sub(r"-\s*\+", "- ", text)
    text = re.sub(r"-\s*-", "+ ", text)
    text = re.sub(r"\+\s*\+", "+ ", text)
    return text


def _clean_math_text(text: str) -> str:
    s = text.replace("\u2212", "-")
    while True:
        prev = s
        s = _clean_math_signs(s)
        if s == prev:
            break
    return s


def _calc_term_body_sign(term: str) -> tuple[int, str]:
    t = str(term).strip()
    if not t:
        return 1, ""
    if t.startswith("+"):
        return 1, t[1:].strip()
    if t.startswith("−") or t.startswith("-"):
        return -1, t[1:].strip()
    return 1, t


def _join_calc_terms(parts: list[str]) -> str:
    parsed: list[tuple[int, str]] = []
    for part in parts:
        part = str(part).strip()
        if not part:
            continue
        sign, body = _calc_term_body_sign(part)
        body = body.strip()
        if body:
            parsed.append((sign, body))
    if not parsed:
        return "0"
    pieces: list[str] = []
    for i, (sign, body) in enumerate(parsed):
        if i == 0:
            pieces.append(f"− {body}" if sign < 0 else body)
        elif sign < 0:
            pieces.append(f"− {body}")
        else:
            pieces.append(f"+ {body}")
    return _clean_math_text(" ".join(pieces))


def _parse_calc_display_number(text: str) -> float:
    return float(str(text).strip().replace(",", ""))


def _expand_parenthetical_inner(inner: str) -> str:
    raw = str(inner).strip()
    if "·" in raw:
        parts = [p.strip() for p in raw.split("·", 1)]
        if len(parts) == 2:
            try:
                return str(
                    solver.format_number(
                        _parse_calc_display_number(parts[0])
                        * _parse_calc_display_number(parts[1])
                    )
                )
            except ValueError:
                pass
    try:
        return str(solver.format_number(_parse_calc_display_number(raw)))
    except ValueError:
        return raw


def _expand_calc_parentheses(eq_text: str) -> str:
    return re.sub(
        r"\(([^)]+)\)",
        lambda m: _expand_parenthetical_inner(m.group(1)),
        _clean_math_text(str(eq_text or "")),
    )
