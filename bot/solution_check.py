# -*- coding: utf-8 -*-
"""שכבת פתרון: מנוע סטטיקה + השוואת תשובת תלמיד לריאקציות."""
from __future__ import annotations

import logging
import re
from typing import Any

from bot.config import KN_PER_TON, VISION_EXTRACT_ONLY_MODE
from bot.vision import (
    format_vision_results_only,
    solve_from_vision_data,
)

log = logging.getLogger("beam_telegram_bot")

DEFAULT_REACTION_TOL_TON = 0.2

_REACTION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"R_Ax\s*[=:]\s*(-?[\d.]+)", "R_Ax"),
    (r"R_Ay\s*[=:]\s*(-?[\d.]+)", "R_Ay"),
    (r"R_Bx\s*[=:]\s*(-?[\d.]+)", "R_Bx"),
    (r"R_By\s*[=:]\s*(-?[\d.]+)", "R_By"),
    (r"R[\s_]*A[\s_]*x\s*[=:]\s*(-?[\d.]+)", "R_Ax"),
    (r"R[\s_]*A[\s_]*y\s*[=:]\s*(-?[\d.]+)", "R_Ay"),
    (r"R[\s_]*B[\s_]*y\s*[=:]\s*(-?[\d.]+)", "R_By"),
    (r"\bAx\s*[=:]\s*(-?[\d.]+)", "R_Ax"),
    (r"\bAy\s*[=:]\s*(-?[\d.]+)", "R_Ay"),
    (r"\bBy\s*[=:]\s*(-?[\d.]+)", "R_By"),
)


def _parse_number(raw: str) -> float | None:
    text = str(raw or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_student_reactions(text: str) -> dict[str, float]:
    """מחלץ ערכי ריאקציה מטקסט חופשי (למשל R_Ay=2.9)."""
    if not text or not str(text).strip():
        return {}
    blob = str(text)
    found: dict[str, float] = {}
    for pattern, key in _REACTION_PATTERNS:
        for match in re.finditer(pattern, blob, flags=re.IGNORECASE):
            val = _parse_number(match.group(1))
            if val is not None:
                found[key] = val
    return found


def _reactions_from_solved(solved: dict[str, Any]) -> dict[str, float]:
    result = solved.get("result") if isinstance(solved.get("result"), dict) else {}
    raw = result.get("reactions_ton") or result.get("reactions_kN") or {}
    out: dict[str, float] = {}
    for key in ("R_Ax", "R_Ay", "R_Bx", "R_By"):
        if key not in raw:
            continue
        try:
            val = float(raw[key])
        except (TypeError, ValueError):
            continue
        if "reactions_kN" in result and "reactions_ton" not in result:
            val /= KN_PER_TON
        out[key] = val
    return out


def compare_student_reactions(
    computed: dict[str, float],
    student: dict[str, float],
    *,
    tol_ton: float = DEFAULT_REACTION_TOL_TON,
) -> list[str]:
    """מחזיר רשימת הבדלים (ריק = התאמה)."""
    if not student:
        return []
    issues: list[str] = []
    labels = {
        "R_Ax": "R_Ax",
        "R_Ay": "R_Ay",
        "R_Bx": "R_Bx",
        "R_By": "R_By",
    }
    for key, label in labels.items():
        if key not in student:
            continue
        exp = computed.get(key)
        got = student[key]
        if exp is None:
            issues.append(f"{label}: לא חושב במנוע")
            continue
        if abs(exp) < 1e-6 and abs(got) < 1e-6:
            continue
        if abs(exp - got) > tol_ton:
            issues.append(f"{label}: קיבלת {got:g}, הנכון {exp:g} (סטייה > {tol_ton:g} ט)")
    return issues


def solve_extracted_beam(extracted: dict[str, Any]) -> dict[str, Any]:
    """מריץ את מנוע הסטטיקה על JSON שחולץ מהתמונה."""
    if VISION_EXTRACT_ONLY_MODE:
        raise ValueError("מצב חילוץ בלבד — חישובים כבויים")
    return solve_from_vision_data(extracted)


def format_solve_reply(extracted: dict[str, Any], solved: dict[str, Any]) -> str:
    """ריאקציות ותוצאות מחושבות בלבד."""
    tool_name = str(solved.get("tool_name", ""))
    result = solved.get("result") or {}
    results = format_vision_results_only(tool_name, result)
    if results.startswith("שגיאה"):
        return results
    return f"*תוצאות:*\n{results}"


def format_student_feedback(
    solved: dict[str, Any],
    student: dict[str, float],
    *,
    tol_ton: float = DEFAULT_REACTION_TOL_TON,
) -> str:
    """משוב בעברית על תשובת תלמיד."""
    computed = _reactions_from_solved(solved)
    if not computed:
        return "לא הצלחתי לחשב ריאקציות לתרגיל האחרון."
    issues = compare_student_reactions(computed, student, tol_ton=tol_ton)
    tool_name = str(solved.get("tool_name", ""))
    correct_block = format_vision_results_only(tool_name, solved.get("result") or {})
    if not issues:
        lines = ["✅ *נכון!* הריאקציות שכתבת תואמות לחישוב לפי השרטוט."]
        if correct_block:
            lines.extend(["", "*ערכים:*", correct_block])
        return "\n".join(lines)
    lines = ["❌ *יש הבדלים בין התשובה שלך לחישוב:*"]
    for issue in issues:
        lines.append(f"• {issue}")
    if correct_block:
        lines.extend(["", "*הערכים הנכונים (לפי השרטוט):*", correct_block])
    return "\n".join(lines)


def try_build_student_check_reply(
    solved: dict[str, Any] | None,
    text: str,
) -> str | None:
    """אם הטקסט מכיל ריאקציות — מחזיר משוב; אחרת None."""
    student = parse_student_reactions(text)
    if not student or not solved:
        return None
    return format_student_feedback(solved, student)
