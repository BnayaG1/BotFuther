# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from notebook_pdf_layout import DEFAULT_BOT_LAYOUT, panel_height_in, point_calc_top_gap_mm

# צבעי «דיו» כמו בתמונת הדוגמה
_INK = "#1a1a1b"
_GREEN = "#188038"
_BLUE = "#0056b3"
_RED = "#d93025"
_PAPER = "#fdf5e6"
_GRID = "#c8c0b0"

# משבצת ריבועית — 11px CSS ≈ 2.91mm על A4
_GRID_CELL_PX = 11
_GRID_CELL_MM = round(_GRID_CELL_PX * 25.4 / 96, 3)

_REACTION_SIGMA_GAP_SQUARES = 7
_REACTION_SIGMA_GAP_MM = round(_REACTION_SIGMA_GAP_SQUARES * _GRID_CELL_MM, 3)

# מרווח בין תמונת הקורה לשורות חישוב הריאקציות (עמוד 1)
_BEAM_TO_CALC_GAP_SQUARES = 2
_BEAM_TO_CALC_GAP_MM = round(_BEAM_TO_CALC_GAP_SQUARES * _GRID_CELL_MM, 3)

_REACTION_CALC_INDENT = "3ch"  # הזחת שורות ריאקציות ימינה — שלושה רווחים
_REACTION_SIGMA_AFTER_COLON_SPACES = 6  # ΣM… (מומנט)
_REACTION_SIGMA_AFTER_COLON_SPACES_F = 8  # ΣF… (כוח)

_EXPORT_DPI = 300
_EMBED_DPI = 150
_BOT_EXPORT_DPI = 150

_NOTEBOOK_FIG_W = 7.8
_NOTEBOOK_FIG_W_WIDE = 11.2
_SUBPLOT_LEFT = 0.09
_SUBPLOT_RIGHT = 0.99
_SUBPLOT_LEFT_WIDE = 0.045
_SUBPLOT_RIGHT_WIDE = 0.995
_BEAM_MAIN_LW = 2.2

_HEADER = "#1e3a5f"
_CHARCOAL = "#2c3e50"
_HIGHLIGHT_ANSWER = "#e2f0d9"
_HIGHLIGHT_ANSWER_BORDER = "#8fad7a"
_ORANGE_NOTE = "#c2410c"
_BRIGHT_GREEN = "#16a34a"

# משבצת אחת בנייר (11px) — בקואורדינטות שרטוט הקורה
_NOTEBOOK_GRID_Y = 0.11
_N_DIAGRAM_SHIFT_SQUARES = 0
_N_DIAGRAM_SHIFT_Y = _N_DIAGRAM_SHIFT_SQUARES * _NOTEBOOK_GRID_Y
_Q_DIAGRAM_SHIFT_SQUARES = 6
_Q_DIAGRAM_SHIFT_Y = _Q_DIAGRAM_SHIFT_SQUARES * _NOTEBOOK_GRID_Y
_M_DIAGRAM_SHIFT_SQUARES = 6
_M_DIAGRAM_SHIFT_Y = _M_DIAGRAM_SHIFT_SQUARES * _NOTEBOOK_GRID_Y

# מכפיל טווח אנכי של דיאגרמות N/Q/M סביב ציר הקורה (y=0).
# <1 = גרף נמתח יותר; >1 = גרף דחוס יותר. 1.0 = ברירת מחדל.
_DIAGRAM_Y_RANGE_MULT = 0.5
# מרווח נוסף בקצוות הציר — מונע חיתוך קווים (קטן יותר כש-mult נמוך)
_DIAGRAM_Y_EDGE_PAD_RATIO = 0.06

_FORCES_FIG_BASE_H = 3.7

# matplotlib משולב (לא נתיב בוט) — גובה פאנל לפי אותו scale כברירת מחדל
_FORCES_PANEL_H_IN = panel_height_in(DEFAULT_BOT_LAYOUT)

# A4 — שוליים מסונכרנים ל-DEFAULT_BOT_LAYOUT
_A4_PAGE_PADDING_TOP_MM = DEFAULT_BOT_LAYOUT.page_padding_top_mm
_A4_PAGE_PADDING_X_MM = DEFAULT_BOT_LAYOUT.page_padding_x_mm
_A4_PAGE_PADDING_BOTTOM_MM = DEFAULT_BOT_LAYOUT.page_padding_bottom_mm
_POINT_CALC_TOP_GAP_MM = point_calc_top_gap_mm(DEFAULT_BOT_LAYOUT)

# יחידות בתצוגת המחברת של הבוט
_U_FORCE = "t"
_U_MOMENT = "tm"

_UI_FONT_CSS = "'Rubik', 'Heebo', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"

_FONT_DIR = Path(__file__).resolve().parent.parent / ".notebook_fonts"
_HEEBO_TTF = _FONT_DIR / "Heebo-Regular.ttf"
_HEEBO_URLS = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/heebo/Heebo-Regular.ttf",
    "https://fonts.gstatic.com/s/heebo/v28/NGs6v5NKh0bT0JCd-1Dh.woff2",
)
_MPL_FONT_FAMILY = "Heebo"
_FONT_READY = False

# גדלי כתב — דיגיטלי וקריא על דף A4 (matplotlib, pt)
_FS_TINY = 8.0
_FS_SMALL = 8.5
_FS_BODY = 9.5
_FS_LABEL = 10.0
_FS_SIGN = 11.0
_FS_TITLE = 10.5
_FS_DIAG_MATH = _FS_LABEL * 1.4
_FS_DIAG_UNIT = _FS_TINY * 1.8
_POINT_CALC_FONT_MULT = 1.8
_FS_POINT_CALC_PT = round(8.5 * _POINT_CALC_FONT_MULT, 1)  # שורות חישובי נקודות (בוט PDF)
_FS_POINT_CALC_TITLE_PT = round(10.0 * _POINT_CALC_FONT_MULT, 1)  # כותרות N/Q/M בעמוד 2
_FS_REACTION_CALC_PT = round(10.0 * _POINT_CALC_FONT_MULT, 1)  # ריאקציות (Σ + שורות + תשובות)

# A4 (210×297 mm) — גובה iframe בפיקסלים (~96 DPI)
_A4_IFRAME_HEIGHT_PX = 1160


def _mm_to_pt(mm: float) -> float:
    """מ\"מ → נקודות PDF (1/72 inch)."""
    return mm * 72.0 / 25.4


def _a4_content_rect(mediabox: Any) -> Any:
    """מלבן תוכן A4 — שוליים קבועים ב-PyMuPDF Story (לא תלוי CSS / wide)."""
    ml = _mm_to_pt(_A4_PAGE_PADDING_X_MM)
    mt = _mm_to_pt(_A4_PAGE_PADDING_TOP_MM)
    mb = _mm_to_pt(_A4_PAGE_PADDING_BOTTOM_MM)
    return mediabox + (ml, mt, -ml, -mb)


def _grid_gap_mm(squares: int) -> float:
    """מרווח במ\"מ לפי מספר משבצות רשת (matplotlib / iframe)."""
    return round(max(0, squares) * _GRID_CELL_MM, 3)

