# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import List, Tuple

import core.statics_calculator as solver


def clean_math_signs(text):
    if not isinstance(text, str):
        return text
    # Replace + followed by any amount of spaces and - with -
    text = re.sub(r"\+\s*-", "- ", text)
    # Replace - followed by any amount of spaces and + with -
    text = re.sub(r"-\s*\+", "- ", text)
    # Replace - followed by any amount of spaces and - with +
    text = re.sub(r"-\s*-", "+ ", text)
    # Replace + followed by any amount of spaces and + with +
    text = re.sub(r"\+\s*\+", "+ ", text)
    return text


def _clean_math_text(text: str) -> str:
    """ניקוי סימנים רק בטקסט מתמטי (לא על HTML / base64 של תמונות)."""
    if not isinstance(text, str):
        return text
    s = text.replace("\u2212", "-")
    while True:
        prev = s
        s = clean_math_signs(s)
        if s == prev:
            break
    return s


def _calc_term_body_sign(term: str) -> Tuple[int, str]:
    """קידומת +/− באיבר (לתצוגה בלבד). מחזיר (sign, body) — sign=+1 או −1."""
    t = str(term).strip()
    if not t:
        return 1, ""
    if t.startswith("+"):
        return 1, t[1:].strip()
    if t.startswith("−"):
        return -1, t[1:].strip()
    if t.startswith("-"):
        return -1, t[1:].strip()
    return 1, t


def _join_calc_terms(parts: List[str]) -> str:
    """חיבור איברי משוואה — חיובי ב־+, שלילי ב־−; ללא «+ −» סמוכים."""
    parsed: List[Tuple[int, str]] = []
    for p in parts:
        p = str(p).strip()
        if not p:
            continue
        sign, body = _calc_term_body_sign(p)
        body = body.strip()
        if body:
            parsed.append((sign, body))
    if not parsed:
        return "0"
    pieces: List[str] = []
    for i, (sign, body) in enumerate(parsed):
        if i == 0:
            pieces.append(f"− {body}" if sign < 0 else body)
        elif sign < 0:
            pieces.append(f"− {body}")
        else:
            pieces.append(f"+ {body}")
    return _clean_math_text(" ".join(pieces))


def _join_eq_value_lines_minus_only(lines: List[str], total: float) -> str:
    """שורות M_i=val / Fx_i=val — חיבור עם +/− וללא «+ −» סמוכים."""
    raw: List[str] = []
    for line in lines:
        line = str(line).strip()
        if not line or "=" not in line:
            if line:
                raw.append(line)
            continue
        lhs, rhs = line.split("=", 1)
        lhs = lhs.strip()
        try:
            v = float(rhs.strip())
        except ValueError:
            raw.append(line)
            continue
        mag = solver.format_number(abs(v))
        raw.append(f"{lhs}={mag}" if v >= 0 else f"{lhs}=-{mag}")
    parts = []
    for r in raw:
        if "=" in r:
            _, rhs = r.split("=", 1)
            rhs = rhs.strip()
            if rhs.startswith("-"):
                parts.append(f"− {rhs[1:].strip()}")
            else:
                parts.append(f"+ {rhs}" if parts else rhs)
    joined = " ".join(parts) if parts else "0"
    return _clean_math_text(f"{joined} = {solver.format_number(total)}")


def _parse_calc_display_number(text: str) -> float:
    """מנסה לקרוא מספר מפורמט (עם פסיקים/רווחים) חזרה ל-float."""
    s = str(text).strip()
    s = s.replace(",", "")
    return float(s)


def _expand_parenthetical_inner(inner: str) -> str:
    """פירוק סוגריים: (a·b) → מכפלה, (n) → n."""
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
    """מחליף כל (…) בערך המפורק — כפל או מספר."""
    return re.sub(
        r"\(([^)]+)\)",
        lambda m: _expand_parenthetical_inner(m.group(1)),
        _clean_math_text(str(eq_text or "")),
    )

