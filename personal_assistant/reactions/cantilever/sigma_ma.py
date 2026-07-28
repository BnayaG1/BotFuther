# -*- coding: utf-8 -*-
"""משוואת שיווי משקל ΣMa = 0 — מוצאים את מומנט הריתום Ma (ריתום)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from bot.draft_format import _fmt_num, _inclined_mag, distributed_span_from_left
from bot.vision import resolve_beam_support_geometry
from core.distributed_moments import (
    UDL_SPLIT_ABOUT_PIVOT_HE,
    distributed_moment_segments_about,
)


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


# במשוואה Ma+Σ=0: כוח שמסתובב עם השעון נכנס במינוס (כדי ש-Ma ייצא נכון).
_MA_CLOCKWISE_POSITIVE = False


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


def _moment_rotation_about_wall_hebrew(
    wall_pos: float, x: float, *, vertical_down: bool
) -> tuple[str, str]:
    clockwise = _vertical_force_rotates_clockwise_about(
        wall_pos, x, vertical_down=vertical_down
    )
    rot_he = "עם" if clockwise else "נגד"
    if _MA_CLOCKWISE_POSITIVE:
        sign = "+" if clockwise else "-"
    else:
        sign = "-" if clockwise else "+"
    return rot_he, sign


def _ma_fixed_product_expr(sign: str, dist_txt: str, force_txt: str) -> str:
    return f"{sign}({dist_txt}·{force_txt})"


def _ma_fixed_product_expr_explain(sign: str, dist_txt: str, force_txt: str) -> str:
    """כמו _ma_fixed_product_expr, אך להצגה בהסבר בלבד — הסימן אחרי הסוגריים."""
    return f"({dist_txt}·{force_txt}){sign}"


def _ma_fixed_product_expr_opened(sign: str, dist: float, force: float) -> str:
    return f"{sign}{_fmt_num(float(dist) * float(force))}"


@dataclass(frozen=True)
class _MaFixedTerm:
    kind: str
    x: float
    dist: float
    force_txt: str
    vertical_down: bool
    ld: dict | None = None
    is_cw_moment: bool | None = None
    """עבור kind=="moment" — הכיוון (עם/נגד השעון) נלקח ישירות מסימן M, לא ממנוף."""
    split_intro: bool = False


def _collect_ma_fixed_terms(
    extracted: dict,
) -> tuple[list[_MaFixedTerm], float]:
    beam = _beam_from_extracted(extracted)
    _, wall_pos, _tip_pos = resolve_beam_support_geometry(beam)
    loads = beam.get("loads") or []
    terms: list[_MaFixedTerm] = []

    if isinstance(loads, list):
        for ld in loads:
            if not isinstance(ld, dict):
                continue
            t = str(ld.get("type", "")).lower()
            if t == "moment":
                m_val = float(ld.get("M", ld.get("m", 0.0)) or 0.0)
                if abs(m_val) < 1e-12:
                    continue
                # #region agent log
                try:
                    import json as _json, time as _time
                    from pathlib import Path as _Path
                    _p = _Path(__file__).resolve().parents[3] / "debug-1522a6.log"
                    with _p.open("a", encoding="utf-8") as _f:
                        _f.write(_json.dumps({"sessionId":"1522a6","hypothesisId":"C","location":"sigma_ma.py:_collect_ma_fixed_terms","message":"JSON moment value","data":{"M":m_val,"is_cw_from_sign":m_val>=0,"x":float(ld.get("x",0.0))},"timestamp":int(_time.time()*1000)})+"\n")
                except Exception:
                    pass
                # #endregion
                terms.append(
                    _MaFixedTerm(
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
                w_raw = float(ld.get("w", ld.get("q", 0.0)) or 0.0)
                segs = distributed_moment_segments_about(w_abs, x1, x2, wall_pos)
                split = len(segs) > 1
                for i, seg in enumerate(segs):
                    if abs(seg.force) < 1e-12 or seg.dist < 1e-12:
                        continue
                    terms.append(
                        _MaFixedTerm(
                            kind="distributed",
                            x=seg.centroid,
                            dist=seg.dist,
                            force_txt=_fmt_num(abs(seg.force)),
                            vertical_down=w_raw >= 0,
                            ld=ld,
                            split_intro=bool(split and i == 0),
                        )
                    )
                continue
            if t == "inclined":
                fy = _inclined_fy_ton(ld)
                if fy < 1e-12:
                    continue
                x = float(ld.get("x", 0.0))
                terms.append(
                    _MaFixedTerm(
                        kind="inclined",
                        x=x,
                        dist=abs(x - wall_pos),
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
                    _MaFixedTerm(
                        kind="point",
                        x=x,
                        dist=abs(x - wall_pos),
                        force_txt=_fmt_num(abs(fy)),
                        vertical_down=fy > 0,
                        ld=ld,
                    )
                )

    terms.sort(key=lambda item: item.x)
    return terms, float(wall_pos)


def _term_rotation_about_wall_hebrew(
    term: _MaFixedTerm, wall_pos: float
) -> tuple[str, str]:
    if term.kind == "moment":
        # מומנט טהור: סימן כמו בשרטוט (עם שעון → + ; נגד שעון → −).
        # תואם statics_calculator כי המשוואה נכתבת Ma+Σ=0 (לא −Ma+Σ=0).
        clockwise = bool(term.is_cw_moment)
        rot_he = "עם" if clockwise else "נגד"
        sign = "+" if clockwise else "-"
        # #region agent log
        try:
            import json as _json, time as _time
            from pathlib import Path as _Path
            _p = _Path(__file__).resolve().parents[3] / "debug-1522a6.log"
            with _p.open("a", encoding="utf-8") as _f:
                _f.write(_json.dumps({"sessionId":"1522a6","runId":"post-fix","hypothesisId":"B","location":"sigma_ma.py:_term_rotation_about_wall","message":"PA moment equation sign","data":{"is_cw_moment":bool(term.is_cw_moment),"rot_he":rot_he,"equation_sign":sign,"force_txt":term.force_txt,"x":term.x},"timestamp":int(_time.time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
        return rot_he, sign
    return _moment_rotation_about_wall_hebrew(
        wall_pos, term.x, vertical_down=term.vertical_down
    )


def _describe_ma_fixed_term_hebrew(
    term: _MaFixedTerm, wall_pos: float, *, first: bool
) -> str:
    rot, sign = _term_rotation_about_wall_hebrew(term, wall_pos)
    dist_txt = _fmt_num(term.dist)

    if term.kind == "moment":
        prod = f"{term.force_txt}{sign}"
        body = (
            f"מומנט טהור בגודל {term.force_txt} שמסתובב {rot} כיוון השעון, "
            f"ולכן הוא נכנס למשוואה כ {prod}."
        )
        if first:
            return f"נתחיל בכח הראשון משמאל, {body}"
        return body

    if term.kind == "distributed":
        prod = _ma_fixed_product_expr_explain(sign, dist_txt, term.force_txt)
        body = (
            f"עומס מפורס שמצאנו שהכח השקול שלו הוא {term.force_txt} נכפיל אותו במרחק {dist_txt}, "
            f"ומכיוון שהוא מסתובב {rot} כיוון השעון, הוא ייכנס"
            f"{' ראשון' if first else ''} למשוואה כ{prod}."
        )
    elif term.kind == "inclined":
        prod = _ma_fixed_product_expr_explain(sign, dist_txt, term.force_txt)
        body = (
            f"עומס אלכסוני שמצאנו שהכח האנכי שלו הוא {term.force_txt}, נכפיל אותו במרחק {dist_txt}, "
            f"ומכיוון שהוא מסתובב {rot} כיוון השעון הוא ייכנס"
            f"{' ראשון' if first else ''} למשוואה כ{prod}."
        )
    else:
        prod = _ma_fixed_product_expr_explain(sign, dist_txt, term.force_txt)
        body = (
            f"עומס נקודתי במשקל {term.force_txt}, נכפיל אותו במרחק {dist_txt}, "
            f"ומכיוון שהוא מסתובב {rot} כיוון השעון הוא ייכנס"
            f"{' ראשון' if first else ''} למשוואה כ{prod}."
        )

    if first:
        return f"נתחיל בכח הראשון משמאל, {body}"
    return body


def build_ma_equation_message_hebrew(extracted: dict, *, prefix: str = "") -> str:
    """הודעה 1: הסבר ספציפי לתרגיל — למה סביב נקודת הריתום, ואיזה עומסים נכנסים."""
    terms, wall_pos = _collect_ma_fixed_terms(extracted)
    vertical_terms = [t for t in terms if t.kind != "moment"]
    moment_terms = [t for t in terms if t.kind == "moment"]

    lines: list[str] = []
    head = f"{prefix} " if prefix else ""
    lines.append(f"{head}נמצא את Ma מהמשוואה ΣMA=0 (סביב נקודת הריתום).")
    count_line = f"בתרגיל שלנו יש {len(vertical_terms)} עומסים אנכיים"
    if moment_terms:
        count_line += f", וגם {len(moment_terms)} עומסי מומנט טהור"
    lines.append(count_line + ".")

    if not terms:
        lines.append("אין כאן עומסים שיכולים להיכנס למשוואה, ולכן Ma יהיה 0.")
        return "\n".join(lines)

    for i, term in enumerate(terms):
        if term.split_intro:
            lines.append(UDL_SPLIT_ABOUT_PIVOT_HE)
        desc = _describe_ma_fixed_term_hebrew(term, wall_pos, first=(i == 0))
        if i == 0:
            lines.append(desc)
        else:
            lines.append(f"הכח הבא הוא {desc}")

    lines.append("תרצה לראות איך כל זה נכנס למשוואה אחת עד הגעה לפתרון?")
    return "\n".join(lines)


def compute_Ma_from_extracted(extracted: dict) -> float:
    """מחזיר Ma [ט·מ] כך ש-ΣMA=0 סביב נקודת הריתום (ראה גם solve_cantilever_beam)."""
    terms, wall_pos = _collect_ma_fixed_terms(extracted)
    known = 0.0
    for term in terms:
        _rot, sign = _term_rotation_about_wall_hebrew(term, wall_pos)
        s = 1.0 if sign == "+" else -1.0
        if term.kind == "moment":
            try:
                force = float(str(term.force_txt).replace(",", ""))
            except (TypeError, ValueError):
                force = 0.0
            known += s * force
        else:
            try:
                force = float(str(term.force_txt).replace(",", ""))
            except (TypeError, ValueError):
                force = 0.0
            known += s * float(term.dist) * force
    # Ma + Σ = 0  ⇒  Ma = −Σ
    return -known


def build_ma_assembled_equation_hebrew(extracted: dict) -> str:
    """הודעה 2: הפירוק — המשוואה המורכבת, פתוחה למספרים, והתוצאה."""
    terms, wall_pos = _collect_ma_fixed_terms(extracted)
    parts: list[str] = ["Ma"]
    opened_parts: list[str] = ["Ma"]
    known = 0.0
    for term in terms:
        _rot, sign = _term_rotation_about_wall_hebrew(term, wall_pos)
        s = 1.0 if sign == "+" else -1.0
        dist_txt = _fmt_num(term.dist)
        if term.kind == "moment":
            expr = f"{sign}{term.force_txt}"
            parts.append(expr)
            opened_parts.append(expr)
            try:
                force = float(str(term.force_txt).replace(",", ""))
            except (TypeError, ValueError):
                force = 0.0
            known += s * force
        else:
            parts.append(_ma_fixed_product_expr(sign, dist_txt, term.force_txt))
            try:
                force = float(str(term.force_txt).replace(",", ""))
            except (TypeError, ValueError):
                force = 0.0
            opened_parts.append(_ma_fixed_product_expr_opened(sign, term.dist, force))
            known += s * float(term.dist) * force
    equation = "".join(parts) + "=0"
    opened = "".join(opened_parts) + "=0"
    ma = -known
    ma_txt = _fmt_num(ma)
    return (
        "ככה נראית המשוואה שלנו:\n"
        f"{equation}\n"
        "כשפותחים את כל האיברים המשוואה תיראה ככה:\n"
        f"{opened}\n"
        "והתוצאה:\n"
        f"Ma = {ma_txt} ט·מ"
    )
