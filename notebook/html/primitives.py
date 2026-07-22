# -*- coding: utf-8 -*-
from __future__ import annotations

import html as html_lib

import core.statics_calculator as solver

from notebook.html.math_format import _clean_math_text


def _nb_line(text: str, css: str = "nb-black") -> str:
    if not str(text).strip():
        return '<p class="nb-line nb-black nb-gap">&nbsp;</p>'
    return f'<p class="nb-line {css}">{html_lib.escape(str(text))}</p>'


def _esc_num(value: float) -> str:
    """format_number → str → html.escape (escape expects str, not int/float)."""
    return html_lib.escape(str(solver.format_number(value)))


def _sym_sigma() -> str:
    return '<span class="nb-sym" aria-label="Sigma">Σ</span>'


def _sym_delta() -> str:
    return '<span class="nb-sym" aria-label="Delta">Δ</span>'


def _nb_step(text: str, css: str = "nb-eq") -> str:
    if not str(text).strip():
        return '<p class="nb-line nb-gap">&nbsp;</p>'
    return f'<p class="nb-line {css}">{html_lib.escape(_clean_math_text(str(text)))}</p>'


def _nb_step_html(inner_html: str, css: str = "nb-eq") -> str:
    """שורת חישוב עם HTML בטוח (Σ, Δ, sub) — ללא escape על התוכן."""
    return f'<p class="nb-line {css}">{inner_html}</p>'


def _nb_step_html_style(inner_html: str, css: str = "nb-eq", style: str = "") -> str:
    """כמו _nb_step_html, אבל עם style inline (ליישור/מרווחים עקביים)."""
    st = f' style="{style}"' if str(style).strip() else ""
    return f'<p class="nb-line {css}"{st}>{inner_html}</p>'


def _nb_calc_eq_row(inner_html: str, line_style: str = "", *, oneline: bool = True) -> str:
    """שורת משוואה — ללא מסגרת על כל השורה."""
    css = "nb-eq nb-eq-oneline" if oneline else "nb-eq"
    return _nb_step_html_style(inner_html, css, line_style)


def _nb_calc_answer_row(inner_html: str, line_style: str = "") -> str:
    """שורה עם תשובת ריאקציה במסגרת בלבד."""
    return _nb_step_html_style(inner_html, "nb-eq nb-ans-only", line_style)

