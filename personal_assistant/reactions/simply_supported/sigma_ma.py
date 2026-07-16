# -*- coding: utf-8 -*-
"""משוואת שיווי משקל ΣMa = 0 — מוצאים את By (2 סמכים)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from bot.draft_format import _fmt_num, _inclined_mag, distributed_span_from_left
from bot.vision import resolve_beam_support_geometry


def _beam_from_extracted(extracted: dict) -> dict:
    beam = extracted.get("beam") if isinstance(extracted, dict) else None
    return beam if isinstance(beam, dict) else {}


def _distributed_equivalent_force_ton(ld: dict, beam: dict) -> tuple[float, float]:
    x1, x2 = distributed_span_from_left(ld, beam)
    w = float(ld.get("w", ld.get("q", ld.get("magnitude", 0.0))) or 0.0)
    length = abs(float(x2) - float(x1))
    return abs(float(w)), length


def _inclined_fy_ton(ld: dict) -> float:
    mag = float(_inclined_mag(ld))
    angle = float(ld.get("angle_deg", 30.0) or 30.0)
    return abs(mag * math.sin(math.radians(angle)))


_MA_CLOCKWISE_POSITIVE = True


def _vertical_force_rotates_clockwise_about(
    pivot_x: float,
    force_x: float,
    *,
    vertical_down: bool,
) -> bool:
    lever = float(force_x) - float(pivot_x)
    if abs(lever) < 1e-12:
        return False
    if vertical_down:
        return lever > 0
    return lever < 0


def _moment_rotation_about_a_hebrew(
    ra_pos: float, x: float, *, vertical_down: bool
) -> tuple[str, str]:
    clockwise = _vertical_force_rotates_clockwise_about(
        ra_pos, x, vertical_down=vertical_down
    )
    rot_he = "עם" if clockwise else "נגד"
    if _MA_CLOCKWISE_POSITIVE:
        sign = "+" if clockwise else "-"
    else:
        sign = "-" if clockwise else "+"
    return rot_he, sign


def _ma_product_expr(sign: str, dist_txt: str, force_txt: str) -> str:
    return f"{sign}({dist_txt}·{force_txt})"


def _ma_product_expr_explain(sign: str, dist_txt: str, force_txt: str) -> str:
    """כמו _ma_product_expr, אך להצגה בהסבר בלבד — הסימן אחרי הסוגריים."""
    return f"({dist_txt}·{force_txt}){sign}"


def _ma_product_expr_opened(sign: str, dist: float, force: float) -> str:
    return f"{sign}{_fmt_num(float(dist) * float(force))}"


def _ma_by_product_expr(sign: str, dist_txt: str) -> str:
    return f"{sign}{dist_txt}By"


@dataclass(frozen=True)
class _MaVerticalTerm:
    kind: str
    x: float
    dist: float
    force_txt: str
    vertical_down: bool
    ld: dict | None = None
    is_cw_moment: bool | None = None
    """עבור kind=="moment" — הכיוון (עם/נגד השעון) נלקח ישירות מסימן M, לא ממנוף."""


def _collect_ma_vertical_terms(
    extracted: dict,
) -> tuple[list[_MaVerticalTerm], float, float]:
    beam = _beam_from_extracted(extracted)
    _, ra_pos, rb_pos = resolve_beam_support_geometry(beam)
    loads = beam.get("loads") or []
    terms: list[_MaVerticalTerm] = []

    by_dist = abs(rb_pos - ra_pos)
    terms.append(
        _MaVerticalTerm(
            kind="by",
            x=float(rb_pos),
            dist=by_dist,
            force_txt="By",
            vertical_down=False,
        )
    )

    if isinstance(loads, list):
        for ld in loads:
            if not isinstance(ld, dict):
                continue
            t = str(ld.get("type", "")).lower()
            if t == "moment":
                m_val = float(ld.get("M", ld.get("m", 0.0)) or 0.0)
                if abs(m_val) < 1e-12:
                    continue
                terms.append(
                    _MaVerticalTerm(
                        kind="moment",
                        x=float(ld.get("x", 0.0)),
                        dist=0.0,
                        force_txt=_fmt_num(abs(m_val)),
                        vertical_down=False,
                        ld=ld,
                        is_cw_moment=(m_val >= 0),
                    )
                )
                continue
            if t == "distributed":
                w_abs, length = _distributed_equivalent_force_ton(ld, beam)
                if w_abs < 1e-12 or length < 1e-12:
                    continue
                x1, x2 = distributed_span_from_left(ld, beam)
                x_centroid = (float(x1) + float(x2)) / 2.0
                force = w_abs * length
                w_raw = float(ld.get("w", ld.get("q", 0.0)) or 0.0)
                terms.append(
                    _MaVerticalTerm(
                        kind="distributed",
                        x=x_centroid,
                        dist=abs(x_centroid - ra_pos),
                        force_txt=_fmt_num(force),
                        vertical_down=w_raw >= 0,
                        ld=ld,
                    )
                )
                continue
            if t == "inclined":
                fy = _inclined_fy_ton(ld)
                if fy < 1e-12:
                    continue
                x = float(ld.get("x", 0.0))
                terms.append(
                    _MaVerticalTerm(
                        kind="inclined",
                        x=x,
                        dist=abs(x - ra_pos),
                        force_txt=_fmt_num(fy),
                        vertical_down=True,
                        ld=ld,
                    )
                )
                continue
            if t == "point":
                try:
                    fy = float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)
                except (TypeError, ValueError):
                    fy = 0.0
                if abs(fy) < 1e-12:
                    continue
                x = float(ld.get("x", 0.0))
                terms.append(
                    _MaVerticalTerm(
                        kind="point",
                        x=x,
                        dist=abs(x - ra_pos),
                        force_txt=_fmt_num(abs(fy)),
                        vertical_down=fy > 0,
                        ld=ld,
                    )
                )

    terms.sort(key=lambda item: item.x)
    return terms, float(ra_pos), float(rb_pos)


def _term_rotation_about_a_hebrew(
    term: _MaVerticalTerm, ra_pos: float
) -> tuple[str, str]:
    if term.kind == "moment":
        # מומנט טהור הוא "זוג כוחות" - התרומה שלו למשוואת שיווי משקל לא תלויה
        # בנקודה שסביבה סוכמים (בניגוד לכוח עם מנוף). לכן היא לא נגזרת ממנוף,
        # אלא נכנסת בכיוון ההפוך לכיוון שהוגדר לו (בהתאם לסימן M שהוזן).
        clockwise = bool(term.is_cw_moment)
        rot_he = "עם" if clockwise else "נגד"
        sign = "-" if clockwise else "+"
        return rot_he, sign
    return _moment_rotation_about_a_hebrew(
        ra_pos, term.x, vertical_down=term.vertical_down
    )


def _describe_ma_vertical_term_hebrew(
    term: _MaVerticalTerm, ra_pos: float, *, first: bool
) -> str:
    rot, sign = _term_rotation_about_a_hebrew(term, ra_pos)
    dist_txt = _fmt_num(term.dist)

    if term.kind == "moment":
        prod = f"{term.force_txt}{sign}"
        body = (
            f"מומנט טהור בגודל {term.force_txt}, נכנס למשוואה כ {prod}."
        )
        if first:
            return f"נתחיל בכח הראשון משמאל, {body}"
        return body

    if term.kind == "by":
        prod = _ma_by_product_expr(sign, dist_txt)
        body = (
            f"הריאקציה By, המרחק שלה מA הוא {dist_txt} והיא מסתובבת {rot} כיוון השעון "
            f"ולכן היא תיכנס למשוואה כ{prod}."
        )
    elif term.kind == "distributed":
        prod = _ma_product_expr_explain(sign, dist_txt, term.force_txt)
        body = (
            f"עומס מפורס שמצאנו שהכח השקול שלו הוא {term.force_txt} נכפיל אותו במרחק {dist_txt}, "
            f"ומכיוון שהוא מסתובב {rot} כיוון השעון, הוא ייכנס"
            f"{' ראשון' if first else ''} למשוואה כ{prod}."
        )
    elif term.kind == "inclined":
        prod = _ma_product_expr_explain(sign, dist_txt, term.force_txt)
        body = (
            f"עומס אלכסוני שמצאנו שהכח האנכי שלו הוא {term.force_txt}, נכפיל אותו במרחק {dist_txt}, "
            f"ומכיוון שהוא מסתובב {rot} כיוון השעון הוא ייכנס"
            f"{' ראשון' if first else ''} למשוואה כ{prod}."
        )
    else:
        prod = _ma_product_expr_explain(sign, dist_txt, term.force_txt)
        body = (
            f"עומס נקודתי במשקל {term.force_txt}, נכפיל אותו במרחק {dist_txt}, "
            f"ומכיוון שהוא מסתובב {rot} כיוון השעון הוא ייכנס"
            f"{' ראשון' if first else ''} למשוואה כ{prod}."
        )

    if first:
        return f"נתחיל בכח הראשון משמאל, {body}"
    return body


def build_by_ma_equation_message_hebrew(extracted: dict, *, prefix: str = "") -> str:
    """הודעה 1: הסבר ספציפי לתרגיל — למה סביב A, ואיזה עומסים נכנסים למשוואה."""
    terms, ra_pos, _rb_pos = _collect_ma_vertical_terms(extracted)
    vertical_terms = [t for t in terms if t.kind not in ("by", "moment")]
    moment_terms = [t for t in terms if t.kind == "moment"]

    lines: list[str] = []
    head = f"{prefix} " if prefix else ""
    lines.append(f"{head}נמצא את By מהמשוואה ΣMA=0 (סביב הנקודה A).")
    count_line = f"בתרגיל שלנו יש {len(vertical_terms)} עומסים אנכיים"
    if moment_terms:
        count_line += f", וגם {len(moment_terms)} עומסי מומנט טהור"
    lines.append(count_line + ".")

    if not terms:
        lines.append("אין כאן עומסים אנכיים לבניית המשוואה.")
        return "\n".join(lines)

    for i, term in enumerate(terms):
        desc = _describe_ma_vertical_term_hebrew(term, ra_pos, first=(i == 0))
        if i == 0:
            lines.append(desc)
        else:
            lines.append(f"הכח הבא הוא {desc}")

    lines.append("תרצה לראות איך כל זה נכנס למשוואה אחת עד הגעה לפתרון?")
    return "\n".join(lines)


def build_by_ma_assembled_equation_hebrew(extracted: dict) -> str:
    """הודעה 2: הפירוק — המשוואה המורכבת, פתוחה למספרים, והתוצאה."""
    terms, ra_pos, _rb_pos = _collect_ma_vertical_terms(extracted)
    parts: list[str] = []
    opened_parts: list[str] = []
    by_coeff = 0.0
    known_moment = 0.0
    for term in terms:
        _rot, sign = _term_rotation_about_a_hebrew(term, ra_pos)
        s = 1.0 if sign == "+" else -1.0
        dist_txt = _fmt_num(term.dist)
        if term.kind == "by":
            by_expr = _ma_by_product_expr(sign, dist_txt)
            parts.append(by_expr)
            opened_parts.append(by_expr)
            by_coeff = s * float(term.dist)
        elif term.kind == "moment":
            expr = f"{sign}{term.force_txt}"
            parts.append(expr)
            opened_parts.append(expr)
            try:
                force = float(str(term.force_txt).replace(",", ""))
            except (TypeError, ValueError):
                force = 0.0
            known_moment += s * force
        else:
            parts.append(_ma_product_expr(sign, dist_txt, term.force_txt))
            try:
                force = float(str(term.force_txt).replace(",", ""))
            except (TypeError, ValueError):
                force = 0.0
            opened_parts.append(_ma_product_expr_opened(sign, term.dist, force))
            known_moment += s * float(term.dist) * force
    equation = "".join(parts) + "=0"
    opened = "".join(opened_parts) + "=0"
    by = (-known_moment / by_coeff) if abs(by_coeff) >= 1e-12 else 0.0
    by_txt = _fmt_num(by)
    return (
        "ככה נראית המשוואה שלנו:\n"
        f"{equation}\n"
        "כשפותחים את כל האיברים המשוואה תיראה ככה:\n"
        f"{opened}\n"
        "והתוצאה:\n"
        f"By = {by_txt}t"
    )
