# -*- coding: utf-8 -*-
"""
פריסת PDF למחברת הבוט (PyMuPDF Story).

חוזה עמודים קבוע:
  עמוד 1 — קורה + חישובי תגובות + דיאגרמות N/Q/M
  עמוד 2 — חישובי נקודות

כללי PyMuPDF (לא לשבור):
  - margin-top חיובי במ"מ בלבד (לא שלילי)
  - page-break-before על בלוק .nb-page-break אחד (לא על גרף בודד)
  - width:100% על תמונות; בלי transform / position:relative
  - page-break-inside:avoid על .nb-forces-zone שלם
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

# משבצת רשת — 11px CSS ≈ 2.91mm
_GRID_CELL_PX = 11
GRID_CELL_MM = round(_GRID_CELL_PX * 25.4 / 96, 3)

A4_HEIGHT_MM = 297.0
FORCES_FIG_BASE_H_IN = 3.7

PAGE_BREAK_HTML = '<div class="nb-page-break"></div>'

PAGE_BREAK_CSS = """
.nb-page-break {
  page-break-before: always;
  break-before: page;
}
"""


@dataclass(frozen=True)
class NotebookPdfLayout:
    """קונפיגורציית פריסה ל-PDF של הבוט בלבד (לא matplotlib / iframe)."""

    gap_after_calc_squares: int = 7
    gap_n_to_q_squares: int = 6
    gap_q_to_m_squares: int = 6
    gap_after_m_squares: int = 4
    point_calc_base_mm: float = round(10 * 25.4 / 96, 3)
    point_calc_gap_scale: float = 0.3  # 70% פחות מרווח מעל חישובי נקודות
    panel_height_scale: float = 1.18  # >~1.20 overflows page 1 with 18pt reaction font
    page_padding_top_mm: float = 7.0
    page_padding_x_mm: float = 6.0
    page_padding_bottom_mm: float = 8.0
    page1_sections: tuple[str, ...] = ("beam", "calc", "forces")
    page2_sections: tuple[str, ...] = ("point_calc",)


DEFAULT_BOT_LAYOUT = NotebookPdfLayout()

# זיז: 3 בלוקי חישוב (Fx, ΣMA, ΣFy) — panel_height_scale נמוך יותר כדי שלא יגלוש עמוד 1
CANTILEVER_BOT_LAYOUT = NotebookPdfLayout(panel_height_scale=1.05)


def grid_gap_mm(squares: int) -> float:
    """מרווח במ\"מ לפי מספר משבצות רשת."""
    return round(max(0, squares) * GRID_CELL_MM, 3)


def forces_gaps_mm(layout: NotebookPdfLayout) -> tuple[float, float, float]:
    """(margin-top לזון N, gap N→Q, gap Q→M) במ\"מ."""
    return (
        grid_gap_mm(layout.gap_after_calc_squares),
        grid_gap_mm(layout.gap_n_to_q_squares),
        grid_gap_mm(layout.gap_q_to_m_squares),
    )


def point_calc_top_gap_mm(layout: NotebookPdfLayout) -> float:
    """מרווח לפני חישובי נקודות (אחרי גרף M)."""
    raw = layout.point_calc_base_mm + grid_gap_mm(layout.gap_after_m_squares)
    return round(raw * layout.point_calc_gap_scale, 3)


def panel_height_in(layout: NotebookPdfLayout) -> float:
    """גובה פאנל גרף בודד (אינץ') — matplotlib figsize height."""
    return (FORCES_FIG_BASE_H_IN / 3.0) * layout.panel_height_scale


def panel_height_mm(layout: NotebookPdfLayout) -> float:
    return panel_height_in(layout) * 25.4


def a4_content_height_mm(layout: NotebookPdfLayout) -> float:
    return A4_HEIGHT_MM - layout.page_padding_top_mm - layout.page_padding_bottom_mm


def estimate_page2_height_mm(
    layout: NotebookPdfLayout,
    *,
    point_calc_min_mm: float = 95.0,
) -> float:
    """הערכת גובה תוכן עמוד 2 (חישובי נקודות בלבד)."""
    return point_calc_top_gap_mm(layout) + point_calc_min_mm


def assert_page2_fits(layout: NotebookPdfLayout) -> None:
    """אזהרה אם תוכן עמוד 2 חורג מגובה A4 הזמין."""
    est = estimate_page2_height_mm(layout)
    avail = a4_content_height_mm(layout)
    if est > avail:
        warnings.warn(
            f"Notebook PDF page 2: estimated {est:.1f}mm content "
            f"exceeds available {avail:.1f}mm — consider lowering panel_height_scale.",
            stacklevel=2,
        )


def build_bot_notebook_extra_html(
    layout: NotebookPdfLayout,
    *,
    calc_html: str,
    forces_html: str,
    point_calc_inner_html: str,
) -> str:
    """עמוד 1 (calc + forces) | page-break | חישובי נקודות."""
    pt_gap = point_calc_top_gap_mm(layout)
    pts_scroll = (
        f'<div class="nb-point-calc-scroll" style="margin-top:{pt_gap}mm">'
        f"{point_calc_inner_html}</div>"
    )
    return calc_html + forces_html + PAGE_BREAK_HTML + pts_scroll
