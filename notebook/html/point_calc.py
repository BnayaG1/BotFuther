# -*- coding: utf-8 -*-
from __future__ import annotations

import html as html_lib
import re
from typing import Any, Dict, List, Optional, Tuple

import solver

from notebook.html.math_format import _clean_math_text, _join_calc_terms
from notebook.html.primitives import _nb_step_html
from notebook.constants import _U_MOMENT


def _point_calc_grid_html(
    rows: List[Dict[str, Any]],
    *,
    loads: List[dict],
    support_mode: str,
    L: float,
    ra_pos: float = 0.0,
    rb_pos: float = 0.0,
    ra_x: float = 0.0,
    ra_y: float = 0.0,
    rb_y: float = 0.0,
    cantilever_result: Optional[Dict[str, Any]] = None,
) -> str:
    """בלוק 3 עמודות: Nx/Qx/Mx בנקודות — עם פירוק "מה שעובר" בנקודה."""

    def _fmt(v: float) -> str:
        return str(solver.format_number(float(v)))

    def _chain_step(prev: float, cur: float) -> str:
        """צעד בדיאגרמה בפורמט קומפקטי: +a / -a / +0."""
        d = float(cur - prev)
        if abs(d) < 1e-9:
            return "+0"
        if d > 0:
            return f"+{_fmt(abs(d))}"
        return f"-{_fmt(abs(d))}"

    def _term_join(terms: List[str]) -> str:
        return _join_calc_terms(terms)

    def _add_signed(terms: List[str], value: float, fragment: str) -> None:
        """איבר עם סימן חיצוני; ערך בתוך סוגריים תמיד בערך מוחלט."""
        if abs(value) < 1e-9:
            return
        op = "+" if value >= 0 else "−"
        terms.append(f"{op} {fragment}")

    def _support_terms_at_x(x: float) -> Tuple[str, str, str]:
        # N(x)
        n_terms: List[str] = [f"Ax({_fmt(ra_x)})"]
        # Q(x)
        q_terms: List[str] = [f"Ay({_fmt(ra_y)})"]
        # M(x)
        m_terms: List[str] = []

        if x >= rb_pos - 1e-9 and abs(rb_y) > 1e-9:
            _add_signed(q_terms, rb_y, f"By({_fmt(abs(rb_y))})")

        # תגובת כוחות למומנט בחתך (רק אם משמאל לחתך)
        m_terms.append(f"Ay({_fmt(abs(ra_y))})·{_fmt(x - ra_pos)}")
        if x >= rb_pos - 1e-9 and abs(rb_y) > 1e-9:
            _add_signed(m_terms, rb_y, f"By({_fmt(abs(rb_y))})·{_fmt(x - rb_pos)}")

        for ld in loads:
            t = ld.get("type")
            if t == "point":
                xi = float(ld.get("x", 0.0) or 0.0)
                if x + 1e-9 < xi:
                    continue
                fx = float(ld.get("Fx", 0.0) or 0.0)
                fy = float(ld.get("Fy", 0.0) or 0.0)
                if abs(fx) > 1e-9:
                    _add_signed(n_terms, fx, f"Fx({_fmt(abs(fx))})")
                if abs(fy) > 1e-9:
                    _add_signed(q_terms, fy, f"Fy({_fmt(abs(fy))})")
                    _add_signed(m_terms, fy, f"Fy({_fmt(abs(fy))})·{_fmt(x - xi)}")
            elif t == "inclined":
                xi = float(ld.get("x", 0.0) or 0.0)
                if x + 1e-9 < xi:
                    continue
                fx = float(ld.get("Fx", 0.0) or 0.0)
                fy = float(ld.get("Fy", 0.0) or 0.0)
                if abs(fx) > 1e-9:
                    _add_signed(n_terms, fx, f"Fx({_fmt(abs(fx))})")
                if abs(fy) > 1e-9:
                    _add_signed(q_terms, fy, f"Fy({_fmt(abs(fy))})")
                    _add_signed(m_terms, fy, f"Fy({_fmt(abs(fy))})·{_fmt(x - xi)}")
            elif t == "distributed":
                x1 = float(ld.get("x1", 0.0) or 0.0)
                x2 = float(ld.get("x2", 0.0) or 0.0)
                w = float(ld.get("w", 0.0) or 0.0)
                if abs(w) < 1e-9 or x + 1e-9 <= x1:
                    continue
                seg = max(0.0, min(x, x2) - x1)
                if seg <= 1e-9:
                    continue
                R = w * seg
                xc = x1 + seg / 2.0
                _add_signed(q_terms, R, f"R({_fmt(abs(R))})")
                _add_signed(m_terms, R, f"R({_fmt(abs(R))})·{_fmt(x - xc)}")
            elif t == "moment":
                xi = float(ld.get("x", 0.0) or 0.0)
                if x + 1e-9 < xi:
                    continue
                mm = float(ld.get("M", 0.0) or 0.0)
                if abs(mm) > 1e-9:
                    _add_signed(m_terms, mm, f"M({_fmt(abs(mm))})")

        return _term_join(n_terms), _term_join(q_terms), _term_join(m_terms)

    def _cantilever_terms_at_x(x: float) -> Tuple[str, str, str]:
        ra_x2 = float(cantilever_result.get("R_Ax", 0.0)) if cantilever_result else 0.0
        ra_y2 = float(cantilever_result.get("R_Ay", 0.0)) if cantilever_result else 0.0
        m_a2 = float(cantilever_result.get("M_A", 0.0)) if cantilever_result else 0.0
        n_terms: List[str] = [f"Ax({_fmt(ra_x2)})"]
        q_terms: List[str] = [f"Ay({_fmt(ra_y2)})"]
        m_terms: List[str] = [f"Ma({_fmt(m_a2)})"]
        _add_signed(m_terms, ra_y2, f"Ay({_fmt(abs(ra_y2))})·{_fmt(x)}")

        for ld in loads:
            t = ld.get("type")
            if t == "point":
                xi = float(ld.get("x", 0.0) or 0.0)
                if x + 1e-9 < xi:
                    continue
                fx = float(ld.get("Fx", 0.0) or 0.0)
                fy = float(ld.get("Fy", 0.0) or 0.0)
                if abs(fx) > 1e-9:
                    _add_signed(n_terms, fx, f"Fx({_fmt(abs(fx))})")
                if abs(fy) > 1e-9:
                    _add_signed(q_terms, fy, f"Fy({_fmt(abs(fy))})")
                    _add_signed(m_terms, fy, f"Fy({_fmt(abs(fy))})·{_fmt(x - xi)}")
            elif t == "inclined":
                xi = float(ld.get("x", 0.0) or 0.0)
                if x + 1e-9 < xi:
                    continue
                fx = float(ld.get("Fx", 0.0) or 0.0)
                fy = float(ld.get("Fy", 0.0) or 0.0)
                if abs(fx) > 1e-9:
                    _add_signed(n_terms, fx, f"Fx({_fmt(abs(fx))})")
                if abs(fy) > 1e-9:
                    _add_signed(q_terms, fy, f"Fy({_fmt(abs(fy))})")
                    _add_signed(m_terms, fy, f"Fy({_fmt(abs(fy))})·{_fmt(x - xi)}")
            elif t == "distributed":
                x1 = float(ld.get("x1", 0.0) or 0.0)
                x2 = float(ld.get("x2", 0.0) or 0.0)
                w = float(ld.get("w", 0.0) or 0.0)
                if abs(w) < 1e-9 or x + 1e-9 <= x1:
                    continue
                seg = max(0.0, min(x, x2) - x1)
                if seg <= 1e-9:
                    continue
                R = w * seg
                xc = x1 + seg / 2.0
                _add_signed(q_terms, R, f"R({_fmt(abs(R))})")
                _add_signed(m_terms, R, f"R({_fmt(abs(R))})·{_fmt(x - xc)}")
            elif t == "moment":
                xi = float(ld.get("x", 0.0) or 0.0)
                if x + 1e-9 < xi:
                    continue
                mm = float(ld.get("M", 0.0) or 0.0)
                if abs(mm) > 1e-9:
                    _add_signed(m_terms, mm, f"M({_fmt(abs(mm))})")

        return _term_join(n_terms), _term_join(q_terms), _term_join(m_terms)

    def _val_with_unit(val: float, *, unit: str = "t") -> str:
        s = _fmt(val)
        if abs(val) < 1e-9:
            return s
        return f"{s}{unit}"

    n_rows: List[str] = []
    q_rows: List[str] = []
    m_rows: List[str] = []
    # מהשורה השנייה: המשוואה מתחילה מתוצאת השורה הקודמת (+/-Δ עד הנקודה הנוכחית)
    prev_printed_n: float | None = None
    prev_printed_q: float | None = None
    prev_printed_m: float | None = None
    for r in rows:
        x = float(r["x"])
        lab = str(r.get("label", ""))
        if support_mode == "cantilever":
            n_expr, q_expr, m_expr = _cantilever_terms_at_x(x)
        else:
            n_expr, q_expr, m_expr = _support_terms_at_x(x)

        n_val = float(r["N"])
        q_val = float(r["Q"])
        m_val = float(r["M"])
        lab_esc = html_lib.escape(lab)

        def _point_row(sym: str, chain: str, val: float, *, unit: str = "t") -> str:
            # כלל: אם הביטוי הוא 0 בשורה הראשונה — להציג רק "= 0" (בלי יחידות, בלי '=' נוסף)
            if abs(val) < 1e-9 and chain.strip() == "0":
                return f"{sym}<sub>{lab_esc}</sub> = 0"
            val_esc = html_lib.escape(_val_with_unit(val, unit=unit))
            chain_esc = html_lib.escape(_clean_math_text(chain))
            return f"{sym}<sub>{lab_esc}</sub> = {chain_esc} = {val_esc}"

        def _step_eq(prev: float, cur: float) -> str:
            """משוואה משורה 2+: תוצאה קודמת ± Δ עד הערך בנקודה הנוכחית."""
            return f"{_fmt(prev)}{_chain_step(prev, cur)}"

        # N
        if prev_printed_n is None:
            if abs(n_val) < 1e-9:
                n_rows.append(_nb_step_html(_point_row("N", "0", n_val, unit="t"), "nb-line"))
            else:
                n_rows.append(
                    _nb_step_html(_point_row("N", f"0{_chain_step(0.0, n_val)}", n_val, unit="t"), "nb-line")
                )
            prev_printed_n = n_val
        elif abs(n_val - prev_printed_n) > 1e-9:
            n_rows.append(
                _nb_step_html(_point_row("N", _step_eq(prev_printed_n, n_val), n_val, unit="t"), "nb-line")
            )
            prev_printed_n = n_val

        # Q
        if prev_printed_q is None:
            if abs(q_val) < 1e-9:
                q_rows.append(_nb_step_html(_point_row("Q", "0", q_val, unit="t"), "nb-line"))
            else:
                q_rows.append(
                    _nb_step_html(_point_row("Q", f"0{_chain_step(0.0, q_val)}", q_val, unit="t"), "nb-line")
                )
            prev_printed_q = q_val
        elif abs(q_val - prev_printed_q) > 1e-9:
            q_rows.append(
                _nb_step_html(_point_row("Q", _step_eq(prev_printed_q, q_val), q_val, unit="t"), "nb-line")
            )
            prev_printed_q = q_val

        # M
        if prev_printed_m is None:
            if abs(m_val) < 1e-9:
                m_rows.append(_nb_step_html(_point_row("M", "0", m_val, unit=_U_MOMENT), "nb-line"))
            else:
                m_rows.append(
                    _nb_step_html(
                        _point_row("M", f"0{_chain_step(0.0, m_val)}", m_val, unit=_U_MOMENT),
                        "nb-line",
                    )
                )
            prev_printed_m = m_val
        elif abs(m_val - prev_printed_m) > 1e-9:
            m_rows.append(
                _nb_step_html(
                    _point_row("M", _step_eq(prev_printed_m, m_val), m_val, unit=_U_MOMENT),
                    "nb-line",
                )
            )
            prev_printed_m = m_val

    def _col_html(title: str, rows_html: List[str]) -> str:
        return (
            '<td class="nb-point-col">'
            f"<h4>{html_lib.escape(title)}</h4>"
            + "\n".join(rows_html)
            + "</td>"
        )

    return (
        '<table class="nb-point-grid">'
        "<tr>"
        + _col_html("N(x) — כוחות ציריים", n_rows)
        + _col_html("Q(x) — גזירה", q_rows)
        + _col_html("M(x) — מומנט", m_rows)
        + "</tr></table>"
    )

