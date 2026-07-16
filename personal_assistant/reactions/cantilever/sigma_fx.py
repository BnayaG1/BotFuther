# -*- coding: utf-8 -*-
"""משוואת שיווי משקל ΣFx = 0 — מוצאים את Ax (ריתום)."""

from __future__ import annotations

import math

from bot.draft_format import _fmt_num, _inclined_dir, _inclined_mag


def _beam_from_extracted(extracted: dict) -> dict:
    beam = extracted.get("beam") if isinstance(extracted, dict) else None
    return beam if isinstance(beam, dict) else {}


def _inclined_fx_ton(ld: dict) -> float:
    mag = float(_inclined_mag(ld))
    angle = float(ld.get("angle_deg", 30.0) or 30.0)
    try:
        fx = mag * math.cos(math.radians(angle))
    except Exception:
        fx = 0.0
    return float(fx)


def compute_Ax_from_extracted(extracted: dict) -> float:
    """מחזיר Ax [t] כך ש-ΣFx=0 (ימינה חיובי)."""
    beam = _beam_from_extracted(extracted)
    loads = beam.get("loads") or []
    if not isinstance(loads, list):
        return 0.0
    sum_fx = 0.0
    for ld in loads:
        if not isinstance(ld, dict):
            continue
        t = str(ld.get("type", "")).lower()
        if t == "inclined":
            fx = _inclined_fx_ton(ld)
            dir_key = _inclined_dir(ld)
            sum_fx += fx if dir_key == "dr" else -fx
            continue
        fx_raw = ld.get("Fx", ld.get("fx"))
        if fx_raw is not None:
            try:
                sum_fx += float(fx_raw)
            except (TypeError, ValueError):
                pass
    return -sum_fx


def _horizontal_load_terms_for_ax_equation(
    extracted: dict,
) -> list[tuple[float, str, str, str]]:
    beam = _beam_from_extracted(extracted)
    loads = beam.get("loads") or []
    entries: list[tuple[float, str, str, str]] = []
    if not isinstance(loads, list):
        return entries
    for ld in loads:
        if not isinstance(ld, dict):
            continue
        t = str(ld.get("type", "")).lower()
        if t == "inclined":
            fx = abs(_inclined_fx_ton(ld))
            if fx < 1e-12:
                continue
            fx_txt = _fmt_num(fx)
            is_right = _inclined_dir(ld) == "dr"
            signed = fx_txt if is_right else f"-{fx_txt}"
            entries.append(
                (
                    float(ld.get("x", 0.0)),
                    signed,
                    ("ימין" if is_right else "שמאל"),
                    ("פלוס" if is_right else "מינוס"),
                )
            )
            continue
        fx_raw = ld.get("Fx", ld.get("fx"))
        if fx_raw is None:
            continue
        try:
            fx = float(fx_raw)
        except (TypeError, ValueError):
            continue
        if abs(fx) < 1e-12:
            continue
        fx_txt = _fmt_num(abs(fx))
        is_right = fx >= 0
        signed = fx_txt if is_right else f"-{fx_txt}"
        entries.append(
            (
                float(ld.get("x", 0.0)),
                signed,
                ("ימין" if is_right else "שמאל"),
                ("פלוס" if is_right else "מינוס"),
            )
        )
    entries.sort(key=lambda item: item[0])
    return entries


def _build_ax_equation_expr(load_terms: list[tuple[float, str, str, str]]) -> str:
    pieces = ["Ax"]
    for _, term, _dir, _sign_word in load_terms:
        if term.startswith("-"):
            pieces.append(term)
        else:
            pieces.append(f"+ {term}")
    return " ".join(pieces) + " = 0"


def build_ax_explain_hebrew(extracted: dict, *, prefix: str = "") -> str:
    """הודעה 1: הסבר ספציפי לתרגיל — בניית משוואת ΣFx=0 עם העומסים הציריים שלנו."""
    head = f"{prefix} " if prefix else ""
    load_terms = _horizontal_load_terms_for_ax_equation(extracted)

    lines: list[str] = [
        f"{head}נמצא את Ax מהמשוואה ΣFx=0.",
    ]

    if not load_terms:
        lines.append("בתרגיל שלנו אין כוחות על ציר הX שהולכים ימינה או שמאלה.")
        lines.append("תרצה לראות איך זה נכנס למשוואה עד הגעה לפתרון?")
        return "\n".join(lines)

    lines.append(f"בתרגיל שלנו יש {len(load_terms)} עומסים ציריים.")
    for i, (_x, term, direction_he, sign_word_he) in enumerate(load_terms, start=1):
        mag = term[1:] if term.startswith("-") else term
        if i == 1:
            lines.append(
                f"נתחיל בעומס הצירי הראשון משמאל שהוא {mag}, ונציב אותו כ{sign_word_he} בגלל שהוא פונה לכיוון {direction_he}."
            )
        else:
            ord_he = "השני" if i == 2 else "השלישי" if i == 3 else f"ה-{i}"
            lines.append(
                f"העומס {ord_he} הוא {mag}, ופונה לכיוון {direction_he}, ולכן נציב אותו במשוואה כ{sign_word_he}."
            )
    lines.append("תרצה לראות איך כל זה נכנס למשוואה אחת עד הגעה לפתרון?")
    return "\n".join(lines)


def build_ax_solution_hebrew(extracted: dict) -> str:
    """הודעה 2: הפירוק — המשוואה המורכבת והתוצאה."""
    load_terms = _horizontal_load_terms_for_ax_equation(extracted)
    ax = compute_Ax_from_extracted(extracted)
    ax_txt = _fmt_num(ax)
    if not load_terms:
        return f"ככה נראית המשוואה שלנו:\nAx = 0\nוהתוצאה:\nAx = {ax_txt}t"
    expr = _build_ax_equation_expr(load_terms)
    return f"ככה נראית המשוואה שלנו:\n{expr}\nוהתוצאה:\nAx = {ax_txt}t"
