# -*- coding: utf-8 -*-
"""תצוגת דף מחברת — מבוסס על תרגיל פתור ידני (שרטוט + דיאגרמות + חישובים).

BOT PATH (Telegram): build_page_html → _notebook_css_for_pdf → PyMuPDF Story → PNG
  פריסת PDF: notebook_pdf_layout.DEFAULT_BOT_LAYOUT (לא iframe CSS / לא transform).

IFRAME PATH (Streamlit תצוגה): _wrap_iframe_document → _NOTEBOOK_IFRAME_CSS (transform על גרפים).
"""
from __future__ import annotations

import base64
import html as html_lib
import io
import math
import re
import sys
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Arc, Polygon
import numpy as np
from matplotlib.lines import Line2D

import solver
from notebook_pdf_layout import (
    DEFAULT_BOT_LAYOUT,
    PAGE_BREAK_CSS,
    NotebookPdfLayout,
    assert_page2_fits,
    build_bot_notebook_extra_html,
    forces_gaps_mm,
    panel_height_in,
    point_calc_top_gap_mm,
)

from notebook.constants import (
    _A4_IFRAME_HEIGHT_PX,
    _BEAM_MAIN_LW,
    _BEAM_TO_CALC_GAP_MM,
    _BLUE,
    _BOT_EXPORT_DPI,
    _BRIGHT_GREEN,
    _CHARCOAL,
    _DIAGRAM_Y_RANGE_MULT,
    _DIAGRAM_Y_EDGE_PAD_RATIO,
    _EMBED_DPI,
    _EXPORT_DPI,
    _FONT_DIR,
    _FONT_READY,
    _FORCES_FIG_BASE_H,
    _FORCES_PANEL_H_IN,
    _FS_BODY,
    _FS_DIAG_MATH,
    _FS_DIAG_UNIT,
    _FS_LABEL,
    _FS_POINT_CALC_PT,
    _FS_POINT_CALC_TITLE_PT,
    _FS_REACTION_CALC_PT,
    _FS_SIGN,
    _FS_SMALL,
    _FS_TITLE,
    _FS_TINY,
    _GREEN,
    _GRID,
    _GRID_CELL_MM,
    _GRID_CELL_PX,
    _HEADER,
    _HEEBO_TTF,
    _HEEBO_URLS,
    _HIGHLIGHT_ANSWER,
    _HIGHLIGHT_ANSWER_BORDER,
    _INK,
    _M_DIAGRAM_SHIFT_SQUARES,
    _M_DIAGRAM_SHIFT_Y,
    _MPL_FONT_FAMILY,
    _NOTEBOOK_FIG_W,
    _NOTEBOOK_FIG_W_WIDE,
    _NOTEBOOK_GRID_Y,
    _N_DIAGRAM_SHIFT_SQUARES,
    _N_DIAGRAM_SHIFT_Y,
    _ORANGE_NOTE,
    _PAPER,
    _POINT_CALC_TOP_GAP_MM,
    _Q_DIAGRAM_SHIFT_SQUARES,
    _Q_DIAGRAM_SHIFT_Y,
    _REACTION_CALC_INDENT,
    _REACTION_SIGMA_AFTER_COLON_SPACES,
    _REACTION_SIGMA_AFTER_COLON_SPACES_F,
    _REACTION_SIGMA_GAP_MM,
    _REACTION_SIGMA_GAP_SQUARES,
    _RED,
    _SUBPLOT_LEFT,
    _SUBPLOT_LEFT_WIDE,
    _SUBPLOT_RIGHT,
    _SUBPLOT_RIGHT_WIDE,
    _U_FORCE,
    _U_MOMENT,
    _UI_FONT_CSS,
    _a4_content_rect,
    _grid_gap_mm,
)


from notebook.css.iframe import NOTEBOOK_IFRAME_CSS as _NOTEBOOK_IFRAME_CSS

_NOTEBOOK_PDF_TYPOGRAPHY_CSS = f"""
* {{ box-sizing: border-box; }}
html, body {{
  margin: 0; padding: 0; background: transparent; direction: ltr;
  font-family: {_UI_FONT_CSS}; color: {_INK};
}}
.nb-outer {{ background: transparent; padding: 0; display: block; }}
.nb-line {{
  margin: 5px 0; padding: 2px 0; line-height: 2.2;
  font-variant-numeric: tabular-nums;
}}
.nb-line.nb-eq {{ color: {_CHARCOAL}; font-weight: 300; }}
.nb-line.nb-eq-oneline {{ white-space: normal; overflow: visible; word-break: break-word; }}
.nb-line.nb-eq-start {{ margin-top: 20px; font-weight: 400; color: {_INK}; }}
.nb-line.nb-eq-start:first-child {{ margin-top: 6px; }}
.nb-sub {{ margin: 8px 0 6px; font-weight: 700; font-size: 10pt; color: {_CHARCOAL}; line-height: 2; }}
.nb-line.nb-delta {{ color: {_BRIGHT_GREEN}; font-weight: 350; font-size: 10.5pt; }}
.nb-line.nb-shear {{ color: {_BLUE}; font-weight: 350; }}
.nb-line.nb-moment {{ color: {_RED}; font-weight: 350; }}
.nb-sym {{
  font-family: 'Rubik', 'Times New Roman', serif; font-weight: 400;
  font-size: 1.05em; line-height: 1; vertical-align: -0.06em;
}}
.nb-box {{
  display: inline-block; border: 1px solid rgba(30, 58, 95, 0.35);
  padding: 4px 12px; margin: 6px 0 10px; font-weight: 700; line-height: 1.65;
  border-radius: 6px; background: rgba(255, 255, 255, 0.35);
}}
.nb-box.nb-box-answer {{
  display: inline-block; max-width: 100%; padding: 1px 6px; margin: 0 1px;
  border-radius: 3px; font-weight: 600; line-height: 1.3;
  background: #edf5ef; border: 1px solid {_GREEN}; color: {_CHARCOAL};
}}
.nb-box.nb-box-answer.nb-ans-ax {{ background: #e8f3ec; border-color: {_GREEN}; }}
.nb-box.nb-box-answer.nb-ans-ay {{ background: #e8f0fa; border-color: {_BLUE}; }}
.nb-box.nb-box-answer.nb-ans-m {{ background: #faecea; border-color: {_RED}; }}
.nb-eq-tail {{ white-space: nowrap; display: inline; }}
.nb-line.nb-eq .nb-box.nb-box-answer {{ margin: 0; padding: 0 5px; vertical-align: baseline; font-size: 0.98em; }}
.nb-calc-block {{ max-width: 100%; min-width: 0; overflow: visible; font-size: {_FS_REACTION_CALC_PT}pt; }}
.nb-rx-table {{ border-collapse: collapse; border: none; width: auto; max-width: 100%; margin: 0; }}
.nb-calc-block .nb-rx-table + .nb-rx-table {{ margin-top: {_REACTION_SIGMA_GAP_MM}mm; }}
.nb-rx-table td {{
  border: none; padding: 0; vertical-align: baseline; line-height: 1.55;
  text-align: left; white-space: nowrap;
}}
.nb-rx-prefix-hide {{ visibility: hidden; }}
.nb-rx-eq-row .nb-rx-body, .nb-rx-eq-row .nb-eq-tail {{ white-space: nowrap; }}
.nb-rx-ans-row .nb-rx-body {{ white-space: nowrap; }}
.nb-rx-expand-row .nb-rx-body, .nb-rx-expand-row .nb-eq-tail {{ white-space: nowrap; }}
.nb-force-wrap {{
  display: block; width: 100%; margin: 0; padding: 0; overflow: visible;
}}
"""

_NOTEBOOK_PDF_LAYOUT_FIX = f"""
html, body, .nb-outer, .nb-page {{
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}}
.nb-page {{
  height: auto;
  min-height: 0;
  max-height: none;
  overflow: visible;
  background: transparent;
  border: none;
  box-shadow: none;
}}
.nb-row {{
  display: block;
  width: 100%;
  height: auto;
  max-height: none;
  overflow: visible;
}}
.nb-col-left {{
  display: block;
  width: 100%;
  height: auto;
  max-height: none;
  overflow: visible;
}}
.nb-beam-zone, .nb-forces-zone, .nb-calc-block, .nb-point-calc-scroll {{
  width: 100%;
  height: auto;
  max-height: none;
  overflow: visible;
  background: transparent;
}}
.nb-forces-zone {{
  page-break-inside: avoid;
  break-inside: avoid;
}}
.nb-forces-zone img {{
  page-break-inside: avoid;
  break-inside: avoid;
}}
{PAGE_BREAK_CSS}
.nb-force-wrap {{
  display: block;
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 0;
  overflow: visible;
}}
.nb-beam-zone img, .nb-forces-zone img, .nb-force-wrap img {{
  display: block;
  width: 100%;
  max-width: 100%;
  height: auto;
  margin: 0;
  padding: 0;
  transform: none;
  object-position: left top;
  background: transparent;
}}
"""

# PyMuPDF — בלי calc(vw), transform, @import או base64 ב־@font-face
# Story תומך רק ב-background-color (לא background-image) — הרשת נדבקת ב-_stamp_notebook_grid_on_pdf
# שולי דף: _a4_content_rect בלבד — לא padding על .nb-page (מניעת כיווץ/כפילות).
_NOTEBOOK_PDF_OVERRIDES = f"""
html, body {{ background: transparent; margin: 0; padding: 0; direction: ltr; }}
.nb-outer {{ background: transparent; padding: 0; display: block; }}
.nb-page .nb-row,
.nb-page .nb-col-left,
.nb-page .nb-beam-zone,
.nb-page .nb-forces-zone,
.nb-page .nb-calc-block,
.nb-page .nb-calc-block > div,
.nb-page .nb-point-calc-scroll {{
  background: transparent;
}}
.nb-row {{ height: auto; max-height: none; width: 100%; }}
.nb-col-left {{ width: 100%; flex: 1 1 100%; overflow: visible; min-width: 0; }}
.nb-beam-zone, .nb-forces-zone {{ overflow: visible; width: 100%; max-width: 100%; }}
.nb-force-wrap {{ display: block; width: 100%; max-width: 100%; margin: 0; overflow: visible; }}
.nb-beam-zone img, .nb-forces-zone img, .nb-force-wrap img {{
  width: 100%;
  max-width: 100%;
  height: auto;
  margin-left: 0;
  transform: none;
  object-position: left top;
  background: transparent;
}}
.nb-calc-block, .nb-calc-block > div {{
  min-width: 0 !important;
  max-width: 100%;
  overflow: visible;
  background: transparent;
}}
.nb-line.nb-eq-oneline {{
  white-space: normal;
  overflow: visible;
  word-break: break-word;
}}
.nb-rx-table {{
  width: auto;
  max-width: 100%;
  border-collapse: collapse;
  margin: 0;
}}
.nb-calc-block .nb-rx-table + .nb-rx-table {{
  margin-top: {_REACTION_SIGMA_GAP_MM}mm;
}}
.nb-rx-table td {{
  border: none;
  padding: 0;
  vertical-align: baseline;
  line-height: 1.55;
  text-align: left;
  white-space: nowrap;
}}
.nb-rx-prefix-hide {{
  visibility: hidden;
}}
.nb-rx-eq-row .nb-rx-body,
.nb-rx-eq-row .nb-eq-tail {{
  white-space: nowrap;
}}
.nb-rx-ans-row .nb-rx-body {{
  white-space: nowrap;
}}
.nb-rx-expand-row .nb-rx-body,
.nb-rx-expand-row .nb-eq-tail {{
  white-space: nowrap;
}}
.nb-rx-expand-row td,
.nb-rx-ans-row td {{
  line-height: 1.3;
}}
.nb-point-calc-scroll {{ overflow: visible; width: 100%; max-width: 100%; margin-top: {_POINT_CALC_TOP_GAP_MM}mm; page-break-before: auto; }}
.nb-point-grid {{
  width: 100%;
  max-width: 100%;
  table-layout: fixed;
  border-collapse: separate;
  border-spacing: 6px 0;
}}
.nb-point-grid td.nb-point-col {{
  width: 33.33%;
  vertical-align: top;
  text-align: left;
  min-width: 0;
  overflow-wrap: anywhere;
  border: 1px dashed rgba(200, 192, 176, 0.55);
  background: transparent;
}}
.nb-point-col h4 {{
  margin: 0 0 4px 0;
  font-size: {_FS_POINT_CALC_TITLE_PT}pt;
  font-weight: 700;
  line-height: 1.35;
  color: {_CHARCOAL};
}}
.nb-point-col .nb-line {{
  white-space: normal;
  word-break: break-word;
  font-size: {_FS_POINT_CALC_PT}pt;
  line-height: 1.55;
}}
"""

# wide=True — רק matplotlib רחב; שולי PDF זהים (_a4_content_rect).
_NOTEBOOK_PDF_WIDE_OVERRIDES = ""


def _notebook_fig_width(*, wide: bool = False) -> float:
    return _NOTEBOOK_FIG_W_WIDE if wide else _NOTEBOOK_FIG_W


def _subplot_lr(*, wide: bool = False) -> tuple[float, float]:
    if wide:
        return _SUBPLOT_LEFT_WIDE, _SUBPLOT_RIGHT_WIDE
    return _SUBPLOT_LEFT, _SUBPLOT_RIGHT


def _pdf_font_face_css() -> str:
    """גופן Heebo מקובץ מקומי — תואם ל־fitz.Archive (לא base64)."""
    if not _HEEBO_TTF.is_file() or _HEEBO_TTF.stat().st_size < 8000:
        return ""
    return (
        "@font-face{font-family:Heebo;src:url(Heebo-Regular.ttf);"
        "font-weight:400;font-style:normal;}"
    )


def _notebook_css_for_pdf(*, wide: bool = False) -> str:
    """CSS ל-PDF בלבד — לא משתמש ב-iframe (שם max-height:297mm גורם לכיווץ)."""
    css = (
        _pdf_font_face_css()
        + _NOTEBOOK_PDF_TYPOGRAPHY_CSS
        + _NOTEBOOK_PDF_OVERRIDES
        + _NOTEBOOK_PDF_LAYOUT_FIX
    )
    if wide:
        css += _NOTEBOOK_PDF_WIDE_OVERRIDES
    return css


def _embedded_ui_font_face_css() -> str:
    """Heebo מוטמע ל-iframe — עברית ומספרים חדים גם ללא רשת."""
    if not _HEEBO_TTF.is_file() or _HEEBO_TTF.stat().st_size < 8000:
        return ""
    data = base64.b64encode(_HEEBO_TTF.read_bytes()).decode("ascii")
    return (
        "@font-face{font-family:'Heebo';src:url(data:font/truetype;charset=utf-8;"
        f"base64,{data}) format('truetype');font-weight:400;font-style:normal;}}"
    )


def clean_math_signs(text):
    from notebook.html.math_format import clean_math_signs as _impl

    return _impl(text)


def _clean_math_text(text: str) -> str:
    from notebook.html.math_format import _clean_math_text as _impl

    return _impl(text)


def _wrap_iframe_document(body: str) -> str:
    _ensure_notebook_font()
    css = _embedded_ui_font_face_css() + _NOTEBOOK_IFRAME_CSS
    return f"""<!DOCTYPE html>
<html lang="he">
<head><meta charset="utf-8"><style>{css}</style></head>
<body><div class="nb-outer"><article class="nb-page">{body}</article></div></body>
</html>"""


def _wrap_pdf_document(body: str, *, wide: bool = False) -> str:
    """HTML לייצוא PDF — CSS תואם PyMuPDF, ללא חיתוך iframe."""
    _ensure_notebook_font()
    css = _notebook_css_for_pdf(wide=wide)
    return f"""<!DOCTYPE html>
<html lang="he" dir="ltr">
<head><meta charset="utf-8"><style>{css}</style></head>
<body><div class="nb-outer"><article class="nb-page">{body}</article></div></body>
</html>"""


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _notebook_grid_png_path(width_pt: float, height_pt: float, *, dpi: int) -> str:
    """PNG זמני: נייר + משבצות ריבועיות לשכבת רקע ב-PDF (Story לא מצייר CSS grid)."""
    import os
    import tempfile

    from PIL import Image, ImageDraw

    w = max(1, int(width_pt / 72.0 * dpi))
    h = max(1, int(height_pt / 72.0 * dpi))
    cell = max(1, round(_GRID_CELL_MM / 25.4 * dpi))
    paper = _hex_to_rgb(_PAPER)
    grid = _hex_to_rgb(_GRID)
    img = Image.new("RGB", (w, h), paper)
    draw = ImageDraw.Draw(img)
    for x in range(0, w, cell):
        draw.line([(x, 0), (x, h)], fill=grid, width=1)
    for y in range(0, h, cell):
        draw.line([(0, y), (w, y)], fill=grid, width=1)
    fd, path = tempfile.mkstemp(suffix="_nb_grid.png")
    os.close(fd)
    img.save(path)
    return path


def _stamp_notebook_grid_on_pdf(pdf_bytes: bytes, *, dpi: int = _BOT_EXPORT_DPI) -> bytes:
    from notebook.export.pdf import _stamp_notebook_grid_on_pdf as _impl

    return _impl(pdf_bytes, dpi=dpi)


def _html_to_pdf_bytes(html: str) -> bytes:
    from notebook.export.pdf import _html_to_pdf_bytes as _impl

    return _impl(html, ensure_notebook_font=_ensure_notebook_font)


def _pdf_to_png_bytes(pdf_bytes: bytes, *, dpi: int = _EXPORT_DPI) -> bytes:
    from notebook.export.png import _pdf_to_png_bytes as _impl

    return _impl(pdf_bytes, dpi=dpi)


def station_labels(
    loads: List[dict], L: float, ra_pos: float, rb_pos: float
) -> List[Tuple[float, str]]:
    xs = solver.critical_x_positions(loads, L, ra_pos, rb_pos)
    labels: Dict[float, str] = {}
    labels[round(ra_pos, 6)] = "A"
    labels[round(rb_pos, 6)] = "B"
    letters = "CDEGHIJKLMNOPQRSTUVWXYZ"
    li = 0
    for x in xs:
        k = round(x, 6)
        if k not in labels:
            labels[k] = letters[li] if li < len(letters) else f"P{li}"
            li += 1
    return [(x, labels[round(x, 6)]) for x in xs]


def _values_at_stations(
    loads: List[dict],
    L: float,
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_x: float,
    rb_y: float,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for x, label in station_labels(loads, L, ra_pos, rb_pos):
        f = solver.internal_forces_at_x(
            x, L, loads, ra_pos, rb_pos, ra_x, ra_y, rb_y
        )
        m_use = f["M_right"] if abs(f["M_right"]) >= abs(f["M_left"]) else f["M_left"]
        n_use = f["N_right"]
        v_use = f["V_right"]
        rows.append(
            {
                "x": x,
                "label": label,
                "N": n_use,
                "Q": v_use,
                "M": m_use,
                **f,
            }
        )
    return rows


def _cantilever_values_at_stations(loads: List[dict], L: float, result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """ערכי N/Q/M בנקודות קריטיות לזיז (x=0..L)."""
    ra_x = float(result.get("R_Ax", 0.0))
    ra_y = float(result.get("R_Ay", 0.0))
    m_a = float(result.get("M_A", 0.0))
    rows: List[Dict[str, Any]] = []
    for x, label in _cantilever_station_labels(loads, L):
        x = float(x)
        n_val = float(solver.normal_force(x, loads, ra_x, 0.0))
        q_val = float(solver.cantilever_shear_force(x, loads, ra_y))
        m_val = float(solver.cantilever_bending_moment(x, loads, ra_y, m_a))
        rows.append({"x": x, "label": label, "N": n_val, "Q": q_val, "M": m_val})
    return rows


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
    from notebook.html.point_calc import _point_calc_grid_html as _impl

    return _impl(
        rows,
        loads=loads,
        support_mode=support_mode,
        L=L,
        ra_pos=ra_pos,
        rb_pos=rb_pos,
        ra_x=ra_x,
        ra_y=ra_y,
        rb_y=rb_y,
        cantilever_result=cantilever_result,
    )


def _load_fx_term(ld: dict) -> float:
    if ld["type"] == "point":
        return float(ld.get("Fx", 0.0))
    if ld["type"] == "inclined":
        return float(ld["Fx"])
    return 0.0


def _load_fy_term(ld: dict) -> float:
    if ld["type"] == "point":
        return float(ld["Fy"])
    if ld["type"] == "distributed":
        return float(ld["w"] * (ld["x2"] - ld["x1"]))
    if ld["type"] == "inclined":
        return float(ld["Fy"])
    return 0.0


def _equilibrium_sections(
    loads: List[dict],
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_y: float,
) -> Dict[str, Any]:
    sums = solver.equilibrium_load_sums(loads, ra_pos, rb_pos)
    arm_b = rb_pos - ra_pos
    arm_a = ra_pos - rb_pos
    fx_lines: List[str] = []
    ma_lines: List[str] = []
    mb_lines: List[str] = []
    for i, ld in enumerate(loads, 1):
        fx = _load_fx_term(ld)
        if abs(fx) > 1e-9:
            fx_lines.append(f"Fx_{i}={solver.format_number(fx)}")
        ma = solver.equilibrium_load_sums([ld], ra_pos, rb_pos)["moment_about_ra"]
        mb = solver.equilibrium_load_sums([ld], ra_pos, rb_pos)["moment_about_rb"]
        if abs(ma) > 1e-9:
            ma_lines.append(f"M_{i}={solver.format_number(ma)}")
        if abs(mb) > 1e-9:
            mb_lines.append(f"M_{i}={solver.format_number(mb)}")
    return {
        "sums": sums,
        "arm_b": arm_b,
        "arm_a": arm_a,
        "fx_lines": fx_lines,
        "ma_lines": ma_lines,
        "mb_lines": mb_lines,
        "fy_check": sums["sum_fy"] + ra_y + rb_y,
        "ra_x": ra_x,
        "ra_y": ra_y,
        "rb_y": rb_y,
    }


def _shear_zero_notes(
    loads: List[dict],
    L: float,
    ra_pos: float,
    rb_pos: float,
    ra_y: float,
    rb_y: float,
) -> List[str]:
    """נקודות שבהן Q=0 תחת מפולג (כמו x=Q/q בתמונה)."""
    notes: List[str] = []
    eps = 1e-6
    for i, ld in enumerate(loads, 1):
        if ld["type"] != "distributed":
            continue
        x1, x2, w = float(ld["x1"]), float(ld["x2"]), float(ld["w"])
        if abs(w) < 1e-9 or x2 - x1 < 1e-9:
            continue
        v_start = solver.shear_force(x1 + eps, loads, ra_y, rb_y, ra_pos, rb_pos)
        q_mag = abs(w)
        if abs(v_start) < 1e-9:
            xz = x1
        else:
            xz = x1 - v_start / w
        if x1 - 0.01 <= xz <= x2 + 0.01:
            notes.append(
                f"קטע מפולג {i}: x = Q/q = {solver.format_number(abs(v_start))}/{solver.format_number(q_mag)} "
                f"= {solver.format_number(xz)} m  (Q=0)"
            )
    if not notes:
        xs = np.linspace(0, L, 400)
        shears = [solver.shear_force(x, loads, ra_y, rb_y, ra_pos, rb_pos) for x in xs]
        for j in range(len(xs) - 1):
            if shears[j] * shears[j + 1] < 0:
                xz = float(xs[j])
                notes.append(f"חיתוך Q=0 בערך x = {solver.format_number(xz)} m")
                break
    return notes


def _download_heebo_ttf() -> None:
    """מוריד Heebo ל-matplotlib ול-iframe (עברית + נוסחאות)."""
    if _HEEBO_TTF.is_file() and _HEEBO_TTF.stat().st_size > 8000:
        return
    _FONT_DIR.mkdir(parents=True, exist_ok=True)
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    urls = list(_HEEBO_URLS)
    try:
        req = urllib.request.Request(
            "https://fonts.googleapis.com/css2?family=Heebo:wght@400&display=swap",
            headers={"User-Agent": "BeamSolver/1.0"},
        )
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            css = resp.read().decode("utf-8", errors="replace")
        m = re.search(r"url\((https://fonts\.gstatic\.com/[^)]+\.ttf)\)", css)
        if m:
            urls.insert(0, m.group(1))
    except (urllib.error.URLError, OSError, TimeoutError):
        pass
    last_err: Exception | None = None
    for url in urls:
        if url.endswith(".woff2"):
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "BeamSolver/1.0"})
            with urllib.request.urlopen(req, context=ctx, timeout=45) as resp:
                data = resp.read()
            if len(data) > 8000:
                _HEEBO_TTF.write_bytes(data)
                return
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_err = exc
    if last_err is not None:
        raise last_err


def _ensure_notebook_font() -> str:
    """טוען Heebo/Rubik ל-matplotlib — טקסט נקי על שרטוט ודיאגרמות."""
    global _FONT_READY, _MPL_FONT_FAMILY
    if _FONT_READY:
        return _MPL_FONT_FAMILY
    try:
        _download_heebo_ttf()
        from matplotlib import font_manager

        font_manager.fontManager.addfont(str(_HEEBO_TTF))
        _MPL_FONT_FAMILY = font_manager.FontProperties(fname=str(_HEEBO_TTF)).get_name()
    except Exception:
        _MPL_FONT_FAMILY = "Segoe UI"
    _FONT_READY = True
    return _MPL_FONT_FAMILY


def _notebook_mpl_rc() -> None:
    family = _ensure_notebook_font()
    plt.rcParams.update(
        {
            "font.family": family,
            "font.sans-serif": [family, "Heebo", "Rubik", "Segoe UI", "Tahoma", "DejaVu Sans"],
            "font.size": _FS_BODY,
            "axes.unicode_minus": False,
        }
    )


def _prep_figure_transparent(fig: Any) -> None:
    """רקע שקוף — תצוגה מוטמעת ב-HTML (רשת CSS של המחברת)."""
    fig.patch.set_facecolor("none")
    fig.patch.set_alpha(0.0)


def _draw_engineering_paper_grid(ax: Any) -> None:
    """רשת משבצות עדינה — נייר הנדסי (כמו ב-CSS של המחברת)."""
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    xspan = max(float(xmax - xmin), 1e-9)
    yspan = max(float(ymax - ymin), 1e-9)
    xstep = max(0.08, round(xspan / 28.0, 2))
    ystep = max(0.04, round(yspan / 18.0, 3))
    x = xstep * math.floor(xmin / xstep)
    while x <= xmax + 1e-9:
        ax.axvline(x, color=_GRID, linewidth=0.35, alpha=0.58, zorder=0)
        x += xstep
    y = ystep * math.floor(ymin / ystep)
    while y <= ymax + 1e-9:
        ax.axhline(y, color=_GRID, linewidth=0.35, alpha=0.58, zorder=0)
        y += ystep


def _prep_figure_notebook_paper(fig: Any) -> None:
    """רקע נייר מחברת + רשת — לייצוא PNG/PDF עצמאי."""
    fig.patch.set_facecolor(_PAPER)
    fig.patch.set_alpha(1.0)
    for ax in fig.get_axes():
        ax.set_facecolor(_PAPER)
        ax.patch.set_alpha(1.0)
        _draw_engineering_paper_grid(ax)
        for spine in ax.spines.values():
            if spine.get_visible():
                spine.set_color(_INK)
        ax.xaxis.label.set_color(_INK)
        ax.yaxis.label.set_color(_INK)
        ax.tick_params(colors=_INK, labelcolor=_INK)
        title = ax.get_title()
        if title:
            ax.title.set_color(_INK)


def _prep_axis_on_paper(ax: Any, *, grid: bool = False) -> None:
    ax.set_facecolor("none")
    ax.patch.set_alpha(0.0)
    if grid:
        ax.grid(True, color=_GRID, alpha=0.45, linewidth=0.45)
        ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#b8b0a0")
    ax.spines["bottom"].set_color("#b8b0a0")
    ax.tick_params(colors="#555", labelsize=6, length=2)


def _draw_station_x_at(
    ax: Any, x: float, y: float, color: str, *, half: float = 0.038
) -> None:
    ax.plot(
        [x - half, x + half],
        [y + half, y - half],
        color=color,
        linewidth=0.9,
        solid_capstyle="round",
        zorder=6,
    )
    ax.plot(
        [x - half, x + half],
        [y - half, y + half],
        color=color,
        linewidth=0.9,
        solid_capstyle="round",
        zorder=6,
    )


def _draw_beam_station_x(ax: Any, x: float, *, half: float = 0.038) -> None:
    """איקס קטן על הקורה בנקודה שמעליה סימון במידה."""
    _draw_station_x_at(ax, x, 0.0, _INK, half=half)


def _draw_arrow(ax: Any, x: float, y0: float, y1: float, color: str, lw: float = 1.3) -> None:
    ax.annotate(
        "",
        xy=(x, y1),
        xytext=(x, y0),
        arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=10),
    )


def _draw_arrow_h(
    ax: Any, x_tail: float, x_tip: float, y: float, color: str, lw: float = 1.1
) -> None:
    """חץ אופקי — קצה (ראש) ב־x_tip."""
    ax.annotate(
        "",
        xy=(x_tip, y),
        xytext=(x_tail, y),
        arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=9),
        zorder=5,
    )


# סמכים — משולש סגור, פרופורציות קומפקטיות (לפני שדרוג ×1.5)
_SUPPORT_TRI_H = 0.30
_SUPPORT_TRI_W = 0.24
_SUPPORT_LW = 0.9
_SUPPORT_DETAIL_LW = 0.55
_ROLLER_CIRCLE_R = 0.042
_ROLLER_CIRCLE_LW = 0.9
_PIN_HATCH_LW = 0.9
_PIN_HATCH_LEN = 0.13
_PIN_HATCH_LEAN = 0.12
# ריתום במחברת — 80% מגודל בסיס (קטן ב-20%)
_CANTILEVER_NB_SUPPORT_SCALE = 0.8
_CANTILEVER_WALL_HALF_H = 0.45 * _CANTILEVER_NB_SUPPORT_SCALE
_CANTILEVER_HATCH_X = 0.18 * _CANTILEVER_NB_SUPPORT_SCALE
_CANTILEVER_HATCH_DROP = 0.08 * _CANTILEVER_NB_SUPPORT_SCALE
_CANTILEVER_WALL_LW = 1.8 * _CANTILEVER_NB_SUPPORT_SCALE
_CANTILEVER_HATCH_LW = 0.9 * _CANTILEVER_NB_SUPPORT_SCALE
# עומסים במחברת — דקים יותר, אורך/גודל ×1.35
_NOTEBOOK_LOAD_LEN_MULT = 1.35
_NOTEBOOK_LOAD_LW_POINT = 0.85
_NOTEBOOK_LOAD_LW_AXIAL = 0.75
_NOTEBOOK_LOAD_LW_INCL = 0.9
_NOTEBOOK_LOAD_LW_UDL_LINE = 1.0
_NOTEBOOK_LOAD_LW_UDL_ARR = 0.7
_NOTEBOOK_LOAD_LW_UDL_MID = 0.6
_NOTEBOOK_LOAD_LW_MOMENT_ARC = 1.0
_NOTEBOOK_LOAD_LW_MOMENT_HEAD = 0.85
_NOTEBOOK_MOMENT_RAD = 0.22
_NOTEBOOK_MOMENT_ARC_MID_DEG = 110.0
_NOTEBOOK_MOMENT_ARC_SPAN_DEG = 180.0 * _NOTEBOOK_LOAD_LEN_MULT
_DIM_LINE_OFFSET = 0.30
_SCHEMATIC_BOTTOM_PAD = 0.16
_N_BELOW_MARGIN = 0.36


_AXIS_GAP_MULT = 1.5


def _notebook_layout() -> Dict[str, float]:
    """מיקומים אנכיים: קורה → מידות → N (2×d) → Q (1.5×d) → M (1.5×d)."""
    beam_to_dim = _SUPPORT_TRI_H + _DIM_LINE_OFFSET + _NOTEBOOK_GRID_Y
    y_dim = -beam_to_dim
    y_lab = y_dim - 0.14
    y_bottom = y_lab - _SCHEMATIC_BOTTOM_PAD
    axis_gap = _AXIS_GAP_MULT * beam_to_dim
    y_n = y_bottom - 2.0 * beam_to_dim - _N_DIAGRAM_SHIFT_Y
    y_q = y_n - axis_gap - _Q_DIAGRAM_SHIFT_Y
    y_m = y_q - axis_gap - _M_DIAGRAM_SHIFT_Y
    return {
        "beam_to_dim": beam_to_dim,
        "y_dim": y_dim,
        "y_lab": y_lab,
        "y_bottom": y_bottom,
        "axis_gap": axis_gap,
        "y_n": y_n,
        "y_q": y_q,
        "y_m": y_m,
        "y_top": 0.72,
        "y_fig_bottom": y_m - _N_BELOW_MARGIN,
    }


_DIM_LW = 1.2
_DIAG_LW = 1.5
_BASELINE_COLOR = "#9a9a9a"
_BASELINE_LW = 0.8
_BASELINE_ALPHA = 0.5
_FILL_ALPHA = 0.12


def _notebook_diagram_scale(values: np.ndarray) -> float:
    """מקדם כוח→שטח שרטוט סביב ציר דיאגרמה (כמו _beam_diagram_ylim)."""
    yr = float(max(np.max(np.abs(values)), 0.5))
    pad = 0.34 * yr
    return 0.28 / (yr + pad)


def _notebook_diagram_extent_bottom(y_ref: float, values: np.ndarray, scale: float) -> float:
    yr = float(max(np.max(np.abs(values)), 0.5))
    pad = 0.34 * yr
    return y_ref - scale * (yr + pad) - 0.08


def _notebook_diagram_series(
    L: float,
    loads: List[dict],
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_y: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[Tuple[float, str]]]:
    positions = solver.critical_x_positions(loads, L, ra_pos, rb_pos)
    xs = solver.beam_plot_x_coords(L, positions)
    normals = np.array([solver.normal_force(x, loads, ra_x, ra_pos) for x in xs])
    shears = np.array([solver.shear_force(x, loads, ra_y, rb_y, ra_pos, rb_pos) for x in xs])
    moments = np.array([solver.bending_moment(x, loads, ra_y, rb_y, ra_pos, rb_pos) for x in xs])
    crit = station_labels(loads, L, ra_pos, rb_pos)
    return xs, normals, shears, moments, crit


def _draw_diagram_zero_line(ax: Any, L: float, y_axis: float) -> None:
    """קו אפס עדין — בסיס לדיאגרמה (לא בצבע הדיו)."""
    ax.plot(
        [0.0, float(L)],
        [y_axis, y_axis],
        color=_BASELINE_COLOR,
        linewidth=_BASELINE_LW,
        alpha=_BASELINE_ALPHA,
        solid_capstyle="round",
        zorder=1,
    )


def _diagram_titles_on_axis(
    ax: Any,
    L: float,
    y_axis: float,
    color: str,
    math_label: str,
    unit: str,
) -> None:
    del color
    Lf = float(L)
    half_grid = 0.5 * _NOTEBOOK_GRID_Y
    ax.text(
        -half_grid,
        y_axis,
        math_label,
        ha="right",
        va="center",
        fontsize=_FS_DIAG_MATH,
        fontweight="600",
        color=_INK,
        zorder=8,
        clip_on=False,
    )
    ax.text(
        Lf + _NOTEBOOK_GRID_Y,
        y_axis,
        unit,
        ha="left",
        va="center",
        fontsize=_FS_DIAG_UNIT,
        fontweight="500",
        color=_INK,
        zorder=8,
        clip_on=False,
    )


def _annotate_step_notebook(
    ax: Any,
    xs: np.ndarray,
    values: np.ndarray,
    y_ref: float,
    scale: float,
    crit: List[Tuple[float, str]],
    color: str,
    *,
    positive_down: bool,
) -> None:
    """ערכים בנקודות קריטיות + במרכז מדרגות ארוכות — בלי חפיפה."""
    xs = np.asarray(xs, dtype=float)
    values = np.asarray(values, dtype=float)
    Lspan = float(xs[-1] - xs[0]) if len(xs) > 1 else float(xs[-1]) or 1.0
    amp = float(max(np.max(np.abs(values)), 0.5)) * scale
    pad_y = max(0.06, 0.28 * amp)

    def _y(v: float) -> float:
        return y_ref - v * scale if positive_down else y_ref + v * scale

    crit_x = [float(x) for x, _ in crit]

    def _place_label(x: float, v: float, *, slot: int) -> None:
        y = _y(v)
        side = 1 if slot % 2 == 0 else -1
        if positive_down:
            ty = y - pad_y if v >= 0 else y + pad_y
            va = "bottom" if v >= 0 else "top"
        else:
            ty = y + pad_y if v >= 0 else y - pad_y
            va = "bottom" if v >= 0 else "top"
        ty += side * 0.03
        ax.text(
            x,
            ty,
            solver.format_number(v),
            ha="center",
            va=va,
            fontsize=_FS_TINY,
            color=color,
            fontweight="500",
            zorder=7,
            clip_on=False,
        )

    for slot, x in enumerate(crit_x):
        idx = int(np.argmin(np.abs(xs - x)))
        _place_label(x, float(values[idx]), slot=slot)

    for i in range(len(xs) - 1):
        seg = float(xs[i + 1] - xs[i])
        if seg < 0.08 * Lspan:
            continue
        if abs(float(values[i + 1] - values[i])) > 1e-6:
            continue
        xm = 0.5 * (float(xs[i]) + float(xs[i + 1]))
        if any(abs(xm - cx) < 0.06 * Lspan for cx in crit_x):
            continue
        _place_label(xm, float(values[i]), slot=i + len(crit_x))


def _annotate_shear_signs_notebook(
    ax: Any, xs: np.ndarray, shears: np.ndarray, y_ref: float, scale: float
) -> None:
    xs = np.asarray(xs, dtype=float)
    shears = np.asarray(shears, dtype=float)
    i = 0
    while i < len(xs) - 1:
        sign = 1 if shears[i] >= 0 else -1
        j = i + 1
        while j < len(xs) - 1 and (shears[j] >= 0) == (sign >= 0):
            j += 1
        x0, x1 = xs[i], xs[j]
        if x1 - x0 > 1e-6:
            xm = 0.5 * (x0 + x1)
            ym = y_ref + 0.5 * (float(shears[i]) + float(shears[j])) * scale
            ax.text(
                xm,
                ym,
                "+" if sign >= 0 else "−",
                ha="center",
                va="center",
                fontsize=_FS_TINY,
                color=_BLUE,
                fontweight="500",
                zorder=5,
            )
        i = j


def _mark_shear_zero_notebook(
    ax: Any, xs: np.ndarray, shears: np.ndarray, y_ref: float
) -> None:
    for j in range(len(xs) - 1):
        v0, v1 = float(shears[j]), float(shears[j + 1])
        if v0 * v1 < 0:
            x0, x1 = float(xs[j]), float(xs[j + 1])
            xz = x0 - v0 * (x1 - x0) / (v1 - v0)
            ax.plot(
                [xz, xz],
                [y_ref - 0.04, y_ref + 0.04],
                color=_BLUE,
                linewidth=0.9,
                alpha=0.65,
                zorder=4,
            )
            ax.text(
                xz,
                y_ref + 0.1,
                f"x={solver.format_number(xz)}",
                ha="center",
                va="bottom",
                fontsize=_FS_TINY,
                color=_BLUE,
                fontweight="500",
                zorder=7,
                clip_on=False,
            )
            return


def _draw_diagram_base(
    ax: Any,
    L: float,
    y_axis: float,
    color: str,
    crit: List[Tuple[float, str]],
) -> None:
    _draw_diagram_zero_line(ax, L, y_axis)


def _draw_n_schematic(
    ax: Any,
    L: float,
    xs: np.ndarray,
    normals: np.ndarray,
    crit: List[Tuple[float, str]],
    layout: Dict[str, float],
) -> float:
    """N(x) במחברת — step + vlines + ערכים (כמו _plot_n_on_beam)."""
    Lf = float(L)
    y_n = layout["y_n"]
    scale = _notebook_diagram_scale(normals)
    ys = y_n - normals * scale

    _draw_diagram_base(ax, L, y_n, _GREEN, crit)
    ax.fill_between(
        xs, ys, y_n, step="post", color=_GREEN, alpha=_FILL_ALPHA, zorder=2
    )
    ax.step(xs, ys, where="post", color=_GREEN, linewidth=_DIAG_LW, zorder=3)
    _annotate_step_notebook(
        ax, xs, normals, y_n, scale, crit, _GREEN, positive_down=True
    )
    _diagram_titles_on_axis(ax, L, y_n, _GREEN, "N(x)", _U_FORCE)
    return _notebook_diagram_extent_bottom(y_n, normals, scale)


def _draw_q_schematic(
    ax: Any,
    L: float,
    xs: np.ndarray,
    shears: np.ndarray,
    crit: List[Tuple[float, str]],
    layout: Dict[str, float],
) -> float:
    """Q(x) במחברת — step + vlines + סימני גזירה (כמו _plot_q_on_beam)."""
    Lf = float(L)
    y_q = layout["y_q"]
    scale = _notebook_diagram_scale(shears)
    ys = y_q + shears * scale

    _draw_diagram_base(ax, L, y_q, _BLUE, crit)
    ax.fill_between(
        xs, y_q, ys, step="post", color=_BLUE, alpha=_FILL_ALPHA, zorder=2
    )
    ax.step(xs, ys, where="post", color=_BLUE, linewidth=_DIAG_LW, zorder=3)
    _annotate_step_notebook(
        ax, xs, shears, y_q, scale, crit, _BLUE, positive_down=False
    )
    _annotate_shear_signs_notebook(ax, xs, shears, y_q, scale)
    _mark_shear_zero_notebook(ax, xs, shears, y_q)
    _diagram_titles_on_axis(ax, L, y_q, _BLUE, "Q(x)", _U_FORCE)
    return _notebook_diagram_extent_bottom(y_q, shears, scale)


def _annotate_moment_notebook(
    ax: Any,
    xs: np.ndarray,
    moments: np.ndarray,
    y_ref: float,
    scale: float,
    crit: List[Tuple[float, str]],
    color: str,
) -> None:
    xs = np.asarray(xs, dtype=float)
    moments = np.asarray(moments, dtype=float)
    amp = float(max(np.max(np.abs(moments)), 0.5)) * scale
    pad_y = max(0.05, 0.26 * amp)
    for slot, (x, _lab) in enumerate(crit):
        idx = int(np.argmin(np.abs(xs - x)))
        v = float(moments[idx])
        y = y_ref - v * scale
        dy = pad_y if slot % 2 == 0 else -pad_y
        ax.text(
            x,
            y - dy if v >= 0 else y + dy,
            solver.format_number(v),
            ha="center",
            va="bottom" if v >= 0 else "top",
            fontsize=_FS_TINY,
            color=color,
            fontweight="500",
            zorder=7,
            clip_on=False,
        )


def _draw_m_schematic(
    ax: Any,
    L: float,
    xs: np.ndarray,
    moments: np.ndarray,
    crit: List[Tuple[float, str]],
    layout: Dict[str, float],
) -> float:
    """M(x) במחברת — עקומה + ערכים (כמו _plot_m_on_beam)."""
    y_m = layout["y_m"]
    scale = _notebook_diagram_scale(moments)
    ys = y_m - moments * scale

    _draw_diagram_base(ax, L, y_m, _RED, crit)
    ax.fill_between(xs, ys, y_m, color=_RED, alpha=_FILL_ALPHA, zorder=2)
    ax.plot(xs, ys, color=_RED, linewidth=_DIAG_LW, zorder=3, solid_capstyle="round")
    _annotate_moment_notebook(ax, xs, moments, y_m, scale, crit, _RED)
    imx = int(np.argmax(np.abs(moments)))
    amp = float(max(np.max(np.abs(moments)), 0.5)) * scale
    pad_y = max(0.05, 0.26 * amp)
    ax.text(
        float(xs[imx]),
        float(ys[imx]) - pad_y * 1.15,
        solver.format_number(float(moments[imx])),
        ha="center",
        va="bottom",
        fontsize=_FS_TINY,
        color=_RED,
        fontweight="600",
        zorder=7,
        clip_on=False,
    )
    _diagram_titles_on_axis(ax, L, y_m, _RED, "M(x)", _U_MOMENT)
    return _notebook_diagram_extent_bottom(y_m, moments, scale)


def _draw_support_triangle(ax: Any, x: float, tri_h: float, tri_w: float) -> float:
    from notebook.mpl.schematic.supports import _draw_support_triangle as _impl

    return _impl(ax, x, tri_h=tri_h, tri_w=tri_w, support_lw=_SUPPORT_LW)


def _draw_pin_support(
    ax: Any,
    x: float,
    tri_h: float = _SUPPORT_TRI_H,
    tri_w: float = _SUPPORT_TRI_W,
) -> None:
    from notebook.mpl.schematic.supports import _draw_pin_support as _impl

    _impl(
        ax,
        x,
        tri_h=tri_h,
        tri_w=tri_w,
        support_lw=_SUPPORT_LW,
        pin_hatch_len=_PIN_HATCH_LEN,
        pin_hatch_lean=_PIN_HATCH_LEAN,
        pin_hatch_lw=_PIN_HATCH_LW,
    )


def _draw_roller_support(
    ax: Any,
    x: float,
    tri_h: float = _SUPPORT_TRI_H,
    tri_w: float = _SUPPORT_TRI_W,
) -> None:
    from notebook.mpl.schematic.supports import _draw_roller_support as _impl

    _impl(
        ax,
        x,
        tri_h=tri_h,
        tri_w=tri_w,
        support_lw=_SUPPORT_LW,
        roller_circle_r=_ROLLER_CIRCLE_R,
        roller_circle_lw=_ROLLER_CIRCLE_LW,
    )


def _weaker_distributed_load_index(loads: List[dict]) -> Optional[int]:
    """אינדקס העומס המפורס החלש — רק כשיש בדיוק שניים."""
    indices = [i for i, ld in enumerate(loads) if ld.get("type") == "distributed"]
    if len(indices) != 2:
        return None
    i0, i1 = indices
    w0 = abs(float(loads[i0].get("w", 0.0) or 0.0))
    w1 = abs(float(loads[i1].get("w", 0.0) or 0.0))
    if abs(w0 - w1) < 1e-9:
        return None
    return i0 if w0 < w1 else i1


def _draw_udl_line(
    ax: Any,
    x1: float,
    x2: float,
    stem: float,
    q_label: str | None = None,
    *,
    y_drop: float = 0.0,
) -> None:
    from notebook.mpl.schematic.loads import _draw_udl_line as _impl

    _impl(
        ax,
        x1,
        x2,
        stem,
        q_label,
        y_drop=y_drop,
        load_lw_udl_line=_NOTEBOOK_LOAD_LW_UDL_LINE,
        load_lw_udl_arr=_NOTEBOOK_LOAD_LW_UDL_ARR,
        load_lw_udl_mid=_NOTEBOOK_LOAD_LW_UDL_MID,
        fs_body=_FS_BODY,
    )


def _moment_arc_thetas(m: float) -> Tuple[float, float]:
    from notebook.mpl.schematic.loads import _moment_arc_thetas as _impl

    return _impl(
        m,
        moment_arc_span_deg=_NOTEBOOK_MOMENT_ARC_SPAN_DEG,
        moment_arc_mid_deg=_NOTEBOOK_MOMENT_ARC_MID_DEG,
    )


def _draw_moment_arc(
    ax: Any,
    x: float,
    m: float,
    scale: float = _NOTEBOOK_MOMENT_RAD,
    *,
    show_value: bool = True,
) -> None:
    from notebook.mpl.schematic.loads import _draw_moment_arc as _impl

    _impl(
        ax,
        x,
        m,
        moment_rad=scale,
        moment_arc_span_deg=_NOTEBOOK_MOMENT_ARC_SPAN_DEG,
        moment_arc_mid_deg=_NOTEBOOK_MOMENT_ARC_MID_DEG,
        load_lw_moment_arc=_NOTEBOOK_LOAD_LW_MOMENT_ARC,
        load_lw_moment_head=_NOTEBOOK_LOAD_LW_MOMENT_HEAD,
        fs_body=_FS_BODY,
        show_value=show_value,
    )


def _draw_loads_like_canvas(ax: Any, loads: List[dict], load_scale: float, *, show_values: bool = False) -> None:
    from notebook.mpl.schematic.loads import _draw_loads_like_canvas as _impl

    _impl(
        ax,
        loads,
        load_scale,
        draw_arrow=_draw_arrow,
        draw_arrow_h=_draw_arrow_h,
        notebook_load_len_mult=_NOTEBOOK_LOAD_LEN_MULT,
        load_lw_point=_NOTEBOOK_LOAD_LW_POINT,
        load_lw_axial=_NOTEBOOK_LOAD_LW_AXIAL,
        load_lw_incl=_NOTEBOOK_LOAD_LW_INCL,
        load_lw_udl_line=_NOTEBOOK_LOAD_LW_UDL_LINE,
        load_lw_udl_arr=_NOTEBOOK_LOAD_LW_UDL_ARR,
        load_lw_udl_mid=_NOTEBOOK_LOAD_LW_UDL_MID,
        load_lw_moment_arc=_NOTEBOOK_LOAD_LW_MOMENT_ARC,
        load_lw_moment_head=_NOTEBOOK_LOAD_LW_MOMENT_HEAD,
        moment_rad=_NOTEBOOK_MOMENT_RAD,
        moment_arc_span_deg=_NOTEBOOK_MOMENT_ARC_SPAN_DEG,
        moment_arc_mid_deg=_NOTEBOOK_MOMENT_ARC_MID_DEG,
        fs_body=_FS_BODY,
        show_values=show_values,
    )


def _draw_notebook_dimension_lines(
    ax: Any,
    stations: List[Tuple[float, str]],
    layout: Dict[str, float],
    *,
    support_pair: Optional[Tuple[float, float]] = None,
    label_offset_squares: float = 0.0,
) -> float:
    y_dim = layout["y_dim"]
    y_lab = layout["y_lab"] - (0.5 + label_offset_squares) * _NOTEBOOK_GRID_Y
    xs = sorted(set(float(x) for x, _ in stations))
    for x in xs:
        if abs(x) > 1e-6 and abs(x - xs[-1]) > 1e-6:
            _draw_beam_station_x(ax, x)
    ax.plot([xs[0], xs[-1]], [y_dim, y_dim], color=_INK, lw=_DIM_LW, zorder=2)
    for x in xs:
        ax.plot([x, x], [y_dim - 0.045, y_dim + 0.045], color=_INK, lw=_DIM_LW)
    for x0, x1 in zip(xs[:-1], xs[1:]):
        seg = x1 - x0
        if seg > 0.02:
            ax.text(
                (x0 + x1) / 2,
                y_dim + 0.09,
                solver.format_number(seg),
                ha="center",
                va="bottom",
                fontsize=_FS_SMALL,
                color=_INK,
            )
    for x, lab in stations:
        ax.text(x, y_lab, lab, ha="center", fontsize=_FS_LABEL, fontweight="normal", color=_INK)
    bottom = y_lab - 0.08
    if support_pair is not None:
        a, b = sorted((float(support_pair[0]), float(support_pair[1])))
        y_sup = y_dim - 4.0 * _NOTEBOOK_GRID_Y
        ax.plot([a, b], [y_sup, y_sup], color=_INK, lw=_DIM_LW, zorder=2)
        ax.plot([a, a], [y_sup, y_sup + 0.14], color=_INK, lw=_DIM_LW)
        ax.plot([b, b], [y_sup, y_sup + 0.14], color=_INK, lw=_DIM_LW)
        ax.text(
            (a + b) / 2,
            y_sup - 0.09,
            solver.format_number(b - a),
            ha="center",
            va="top",
            fontsize=_FS_SMALL,
            color=_INK,
        )
        bottom = min(bottom, y_sup - 0.16)
    return bottom


def _draw_beam_schematic(
    ax: Any,
    L: float,
    loads: List[dict],
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_y: float,
    *,
    show_values: bool = False,
    set_limits: bool = True,
) -> None:
    from notebook.mpl.schematic.beam import _draw_beam_schematic as _impl

    _impl(
        ax,
        L,
        loads,
        ra_pos,
        rb_pos,
        ra_x,
        ra_y,
        rb_y,
        show_values=show_values,
        set_limits=set_limits,
        station_labels_fn=station_labels,
        notebook_layout_fn=_notebook_layout,
        draw_notebook_dimension_lines_fn=_draw_notebook_dimension_lines,
        draw_pin_support_fn=_draw_pin_support,
        draw_roller_support_fn=_draw_roller_support,
        draw_loads_like_canvas_fn=_draw_loads_like_canvas,
        beam_x_pad_fn=lambda Lf: max(0.15, 0.04 * float(Lf)),
        fs_small=_FS_SMALL,
        fs_body=_FS_BODY,
    )


def _draw_cantilever_wall_support(ax: Any) -> None:
    h = _CANTILEVER_WALL_HALF_H
    span = 2.0 * h
    ax.plot([0, 0], [-h, h], color=_INK, linewidth=_CANTILEVER_WALL_LW, zorder=3)
    for i in range(6):
        yy = -h + span * (i / 5)
        ax.plot(
            [-_CANTILEVER_HATCH_X, 0],
            [yy - _CANTILEVER_HATCH_DROP, yy],
            color=_INK,
            linewidth=_CANTILEVER_HATCH_LW,
            zorder=3,
        )


def _draw_cantilever_beam_schematic(
    ax: Any,
    L: float,
    loads: List[dict],
    *,
    ra_y: float = 0.0,
    set_limits: bool = True,
) -> None:
    """קורת זיז + עומסים — אותו ylim וקנה מידה כמו סמכים (עומסים דקים)."""
    Lf = float(L)
    ax.plot([0, Lf], [0, 0], color=_INK, linewidth=_BEAM_MAIN_LW, zorder=2, solid_capstyle="round")
    _draw_cantilever_wall_support(ax)
    load_scale = max(0.28, 0.05 * max(abs(float(ra_y)), 8.0))
    _draw_loads_like_canvas(ax, loads, load_scale, show_values=False)
    stations = _cantilever_station_labels(loads, L)
    layout = _notebook_layout()
    dim_bottom = _draw_notebook_dimension_lines(ax, stations, layout, label_offset_squares=0.5)
    pad_x = max(0.3 * _CANTILEVER_NB_SUPPORT_SCALE, 0.04 * Lf)
    ax.set_xlim(-pad_x, Lf + max(0.2, 0.03 * Lf))
    if set_limits:
        ax.set_ylim(min(layout["y_bottom"], dim_bottom), layout["y_top"])
    ax.axis("off")


def _beam_x_pad(Lf: float) -> float:
    return max(0.04, 0.015 * float(Lf))


def _diagram_half_extent(peak: float, *, pad_ratio: float) -> float:
    """חצי-טווח ציר: mult=1 רחב, mult→0 צמוד לשיא (מתיחה גלויה, בלי לחתוך נתונים)."""
    yr = float(max(peak, 0.5))
    pad = pad_ratio * yr
    min_pad = 0.05 * yr
    loose = yr + pad
    tight = yr + min_pad
    t = float(_DIAGRAM_Y_RANGE_MULT)
    return tight + t * (loose - tight)


def _diagram_pad_eff(peak: float, *, pad_ratio: float) -> float:
    """מרווח M חד-צדדי — אותה לוגיקת mult כמו _diagram_half_extent."""
    yr = float(max(peak, 0.5))
    pad = max(pad_ratio * yr, 0.08)
    min_pad = max(0.05 * yr, 0.04)
    t = float(_DIAGRAM_Y_RANGE_MULT)
    return min_pad + t * (pad - min_pad)


def _inflate_diagram_ylim(ymin: float, ymax: float) -> Tuple[float, float]:
    """מרווח קטן מעל/מתחת לנתונים — מונע חיתוך קווים בקצה הציר."""
    if _DIAGRAM_Y_EDGE_PAD_RATIO <= 0:
        return ymin, ymax
    half = (ymax - ymin) * 0.5
    edge_scale = max(_DIAGRAM_Y_RANGE_MULT, 0.35)
    pad = half * _DIAGRAM_Y_EDGE_PAD_RATIO * edge_scale
    return ymin - pad, ymax + pad


def _beam_diagram_ylim(values: np.ndarray, *, floor: float = 0.5) -> Tuple[float, float]:
    """טווח אנכי סביב הקורה (y=0) — לא ציר קרטזי."""
    yr = float(max(np.max(np.abs(np.asarray(values, dtype=float))), floor))
    extent = _diagram_half_extent(yr, pad_ratio=0.34)
    return _inflate_diagram_ylim(-extent, extent)


def _beam_diagram_ylim_moment(values: np.ndarray, *, floor: float = 0.5) -> Tuple[float, float]:
    """טווח M — צמוד יותר כשכל הערכים בצד אחד של הקורה (לא מבזבז חצי גובה)."""
    m = np.asarray(values, dtype=float)
    lo = float(np.min(m))
    hi = float(np.max(m))
    peak = float(max(np.max(np.abs(m)), floor))
    pad_eff = _diagram_pad_eff(peak, pad_ratio=0.16)
    if lo >= -1e-6:
        ymin, ymax = -pad_eff, hi + pad_eff
    elif hi <= 1e-6:
        ymin, ymax = lo - pad_eff, pad_eff
    else:
        extent = _diagram_half_extent(peak, pad_ratio=0.34)
        return _inflate_diagram_ylim(-extent, extent)
    return _inflate_diagram_ylim(ymin, ymax)


def _configure_beam_diagram_ax(
    ax: Any,
    Lf: float,
    x_pad: float,
    values: np.ndarray,
    *,
    transparent: bool = True,
    paper: bool = False,
) -> Tuple[float, float]:
    """מגדיר מערכת צירים: x לאורך הקורה, y לגודל הכוח — ללא רשת."""
    if transparent and not paper:
        ax.set_facecolor("none")
        ax.patch.set_alpha(0.0)
    elif paper:
        ax.set_facecolor(_PAPER)
        ax.patch.set_alpha(1.0)
    else:
        ax.set_facecolor(_PAPER)
        ax.patch.set_alpha(1.0)
    ymin, ymax = _beam_diagram_ylim(values)
    ax.set_xlim(-x_pad, Lf + x_pad)
    ax.set_ylim(ymin, ymax)
    if not transparent:
        _draw_engineering_paper_grid(ax)
    return ymin, ymax


def _draw_beam_reference(
    ax: Any,
    Lf: float,
    crit: List[Tuple[float, str]],
    ymin: float,
    ymax: float,
) -> None:
    """קו הקורה — בסיס לדיאגרמה; סימוני נקודות על הקורה בלבד."""
    ax.plot([0, Lf], [0, 0], color=_INK, linewidth=_BEAM_MAIN_LW, zorder=5, solid_capstyle="round")
    ax.axis("off")


def _plot_zero_baseline_cartesian(ax: Any, Lf: float) -> None:
    ax.axhline(
        0.0,
        color=_BASELINE_COLOR,
        linewidth=_BASELINE_LW,
        alpha=_BASELINE_ALPHA,
        zorder=1,
    )


def _plot_n_on_beam(
    ax: Any,
    xs: np.ndarray,
    normals: np.ndarray,
    Lf: float,
    x_pad: float,
    crit: List[Tuple[float, str]],
    *,
    transparent: bool = True,
    paper: bool = False,
) -> None:
    _configure_beam_diagram_ax(ax, Lf, x_pad, normals, transparent=transparent, paper=paper)
    _plot_zero_baseline_cartesian(ax, Lf)
    ax.fill_between(
        xs, normals, 0, step="post", color=_GREEN, alpha=_FILL_ALPHA, zorder=2
    )
    ax.step(xs, normals, where="post", color=_GREEN, linewidth=_DIAG_LW, zorder=3)
    ax.invert_yaxis()
    ymin, ymax = ax.get_ylim()
    _draw_beam_reference(ax, Lf, crit, ymin, ymax)
    _annotate_step_blocks(ax, xs, normals, _GREEN, crit, invert_y=True)


def _plot_q_on_beam(
    ax: Any,
    xs: np.ndarray,
    shears: np.ndarray,
    Lf: float,
    x_pad: float,
    crit: List[Tuple[float, str]],
    *,
    transparent: bool = True,
    paper: bool = False,
) -> None:
    _configure_beam_diagram_ax(ax, Lf, x_pad, shears, transparent=transparent, paper=paper)
    _plot_zero_baseline_cartesian(ax, Lf)
    ax.fill_between(
        xs, shears, 0, step="post", color=_BLUE, alpha=_FILL_ALPHA, zorder=2
    )
    ax.step(xs, shears, where="post", color=_BLUE, linewidth=_DIAG_LW, zorder=3)
    ymin, ymax = ax.get_ylim()
    _draw_beam_reference(ax, Lf, crit, ymin, ymax)
    _annotate_step_blocks(ax, xs, shears, _BLUE, crit)
    _annotate_shear_signs(ax, xs, shears)
    _mark_shear_zero(ax, xs, shears, Lf)


def _plot_m_on_beam(
    ax: Any,
    xs: np.ndarray,
    moments: np.ndarray,
    Lf: float,
    x_pad: float,
    crit: List[Tuple[float, str]],
    *,
    transparent: bool = True,
    paper: bool = False,
) -> None:
    _configure_beam_diagram_ax(ax, Lf, x_pad, moments, transparent=transparent, paper=paper)
    _plot_zero_baseline_cartesian(ax, Lf)
    ax.fill_between(xs, moments, 0, color=_RED, alpha=_FILL_ALPHA, zorder=2)
    ax.plot(xs, moments, color=_RED, linewidth=_DIAG_LW, zorder=3, solid_capstyle="round")
    ax.invert_yaxis()
    ymin, ymax = ax.get_ylim()
    _draw_beam_reference(ax, Lf, crit, ymin, ymax)
    for slot, (x, _lab) in enumerate(crit):
        idx = int(np.argmin(np.abs(xs - x)))
        v = float(moments[idx])
        amp = float(max(np.max(np.abs(moments)), 0.5))
        pad_y = max(0.05, 0.24 * amp)
        dy = pad_y if slot % 2 == 0 else -pad_y
        ax.text(
            x,
            v - dy,
            solver.format_number(v),
            ha="center",
            va="bottom",
            fontsize=_FS_TINY,
            color=_RED,
            fontweight="500",
            zorder=7,
            clip_on=False,
        )
    imx = int(np.argmax(np.abs(moments)))
    yr = float(max(np.max(np.abs(moments)), 0.5))
    pad_y = max(0.05, 0.26 * yr)
    ax.text(
        float(xs[imx]),
        float(moments[imx]) - pad_y,
        solver.format_number(float(moments[imx])),
        ha="center",
        va="bottom",
        fontsize=_FS_TINY,
        color=_RED,
        fontweight="600",
        zorder=7,
    )


def _mpl_hebrew(text: str) -> str:
    """סדר תווים ויזואלי לעברית ב-matplotlib (LTR renderer)."""
    if not text or not re.search(r"[\u0590-\u05FF]", text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except ImportError:
        try:
            from bidi.algorithm import get_display

            return get_display(text)
        except ImportError:
            return text


def _diagram_titles(
    fig: Any,
    ax: Any,
    math_label: str,
    unit: str,
    color: str,
    *,
    Lf: Optional[float] = None,
) -> None:
    """שם מתמטי משמאל, יחידה מימין (חצי משבצת מקצה הקורה) — שחור."""
    del color
    half_grid = 0.5 * _NOTEBOOK_GRID_Y
    if Lf is not None:
        ax.text(
            -half_grid,
            0.0,
            math_label,
            ha="right",
            va="center",
            fontsize=_FS_DIAG_MATH,
            fontweight="600",
            color=_INK,
            zorder=9,
            clip_on=False,
        )
        ax.text(
            float(Lf) + _NOTEBOOK_GRID_Y,
            0.0,
            unit,
            ha="left",
            va="center",
            fontsize=_FS_DIAG_UNIT,
            fontweight="500",
            color=_INK,
            zorder=9,
            clip_on=False,
        )
        return
    bb = ax.get_position()
    fig.text(
        bb.x0 - 0.018,
        bb.y0 + bb.height / 2,
        math_label,
        ha="right",
        va="center",
        fontsize=_FS_DIAG_MATH,
        fontweight="600",
        color=_INK,
    )
    fig.text(
        bb.x1 + 0.006,
        bb.y0 + bb.height / 2,
        unit,
        ha="left",
        va="center",
        fontsize=_FS_DIAG_UNIT,
        fontweight="500",
        color=_INK,
    )


def _diagram_side_labels(fig: Any, ax: Any, left_txt: str, right_txt: str) -> None:
    """תוויות מינימליות בלבד: שם משמאל ויחידה מימין."""
    bb = ax.get_position()
    fs = float(_FS_SMALL) * 1.8
    fig.text(
        bb.x0 - 0.012,
        bb.y0 + bb.height / 2,
        left_txt,
        ha="right",
        va="center",
        fontsize=fs,
        fontweight="600",
        color=_INK,
    )
    fig.text(
        bb.x1 + 0.020,
        bb.y0 + bb.height / 2,
        right_txt,
        ha="left",
        va="center",
        fontsize=fs,
        fontweight="600",
        color=_INK,
    )


def _plot_n_on_beam_clean(
    ax: Any,
    xs: np.ndarray,
    normals: np.ndarray,
    Lf: float,
    x_pad: float,
    crit: List[Tuple[float, str]],
    *,
    transparent: bool = True,
) -> None:
    from notebook.mpl.diagrams.clean import _plot_n_on_beam_clean as _impl

    _impl(
        ax,
        xs,
        normals,
        Lf,
        x_pad,
        crit,
        configure_beam_diagram_ax=_configure_beam_diagram_ax,
        plot_zero_baseline_cartesian=_plot_zero_baseline_cartesian,
        draw_beam_reference=_draw_beam_reference,
        diag_lw=_DIAG_LW,
        fill_alpha=_FILL_ALPHA,
        transparent=transparent,
    )


def _plot_q_on_beam_clean(
    ax: Any,
    xs: np.ndarray,
    shears: np.ndarray,
    Lf: float,
    x_pad: float,
    crit: List[Tuple[float, str]],
    *,
    transparent: bool = True,
) -> None:
    from notebook.mpl.diagrams.clean import _plot_q_on_beam_clean as _impl

    _impl(
        ax,
        xs,
        shears,
        Lf,
        x_pad,
        crit,
        configure_beam_diagram_ax=_configure_beam_diagram_ax,
        plot_zero_baseline_cartesian=_plot_zero_baseline_cartesian,
        draw_beam_reference=_draw_beam_reference,
        diag_lw=_DIAG_LW,
        fill_alpha=_FILL_ALPHA,
        transparent=transparent,
    )


def _plot_m_on_beam_clean(
    ax: Any,
    xs: np.ndarray,
    moments: np.ndarray,
    Lf: float,
    x_pad: float,
    crit: List[Tuple[float, str]],
    *,
    transparent: bool = True,
) -> None:
    from notebook.mpl.diagrams.clean import _plot_m_on_beam_clean as _impl

    _impl(
        ax,
        xs,
        moments,
        Lf,
        x_pad,
        crit,
        configure_beam_diagram_ax=_configure_beam_diagram_ax,
        beam_diagram_ylim_moment=_beam_diagram_ylim_moment,
        plot_zero_baseline_cartesian=_plot_zero_baseline_cartesian,
        draw_beam_reference=_draw_beam_reference,
        diag_lw=_DIAG_LW,
        fill_alpha=_FILL_ALPHA,
        transparent=transparent,
    )
    ax.invert_yaxis()
    ymin, ymax = ax.get_ylim()
    _draw_beam_reference(ax, Lf, crit, ymin, ymax)


def _annotate_step_blocks(
    ax: Any,
    xs: np.ndarray,
    ys: np.ndarray,
    color: str,
    crit: Optional[List[Tuple[float, str]]] = None,
    *,
    invert_y: bool = False,
) -> None:
    """ערכים בנקודות קריטיות ובמדרגות ארוכות — ללא כפילות."""
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    values = ys
    Lspan = float(xs[-1] - xs[0]) if len(xs) > 1 else float(xs[-1]) or 1.0
    amp = float(max(np.max(np.abs(values)), 0.5))
    pad_y = max(0.06, 0.22 * amp)
    crit_x = [float(x) for x, _ in (crit or [])]

    def _label_y(v: float, slot: int) -> float:
        side = 1 if slot % 2 == 0 else -1
        off = pad_y * (1 if v >= 0 else -1)
        if invert_y:
            off = -off
        return v + off + side * 0.02 * amp

    for slot, x in enumerate(crit_x):
        idx = int(np.argmin(np.abs(xs - x)))
        v = float(values[idx])
        ax.text(
            x,
            _label_y(v, slot),
            solver.format_number(v),
            ha="center",
            va="bottom" if v >= 0 else "top",
            fontsize=_FS_TINY,
            color=color,
            fontweight="500",
            zorder=7,
            clip_on=False,
        )

    for i in range(len(xs) - 1):
        seg = float(xs[i + 1] - xs[i])
        if seg < 0.08 * Lspan:
            continue
        if abs(float(values[i + 1] - values[i])) > 1e-6:
            continue
        xm = 0.5 * (float(xs[i]) + float(xs[i + 1]))
        if any(abs(xm - cx) < 0.06 * Lspan for cx in crit_x):
            continue
        v = float(values[i])
        ax.text(
            xm,
            _label_y(v, i + len(crit_x)),
            solver.format_number(v),
            ha="center",
            va="bottom" if v >= 0 else "top",
            fontsize=_FS_TINY,
            color=color,
            fontweight="500",
            zorder=7,
            clip_on=False,
        )


def _annotate_at_critical_x(
    ax: Any,
    xs: np.ndarray,
    ys: np.ndarray,
    crit: List[Tuple[float, str]],
    color: str,
    *,
    y_offset: float = 0.0,
) -> None:
    """ערך בכל נקודה קריטית (על הקו)."""
    for x, _lab in crit:
        idx = int(np.argmin(np.abs(xs - x)))
        v = float(ys[idx])
        ax.annotate(
            solver.format_number(v),
            (x, v),
            textcoords="offset points",
            xytext=(0, y_offset),
            ha="center",
            va="bottom",
            fontsize=_FS_TINY,
            color=color,
            fontweight="500",
            zorder=6,
        )


def _annotate_shear_signs(ax: Any, xs: np.ndarray, shears: np.ndarray) -> None:
    """סימני + / − באזורי גזירה חיוביים/שליליים."""
    xs = np.asarray(xs, dtype=float)
    shears = np.asarray(shears, dtype=float)
    i = 0
    while i < len(xs) - 1:
        sign = 1 if shears[i] >= 0 else -1
        j = i + 1
        while j < len(xs) - 1 and (shears[j] >= 0) == (sign >= 0):
            j += 1
        x0, x1 = xs[i], xs[j]
        if x1 - x0 > 1e-6:
            xm = 0.5 * (x0 + x1)
            ym = 0.5 * (float(shears[i]) + float(shears[j]))
            label = "+" if sign >= 0 else "−"
            ax.text(
                xm,
                ym,
                label,
                ha="center",
                va="center",
                fontsize=_FS_TINY,
                color=_BLUE,
                fontweight="500",
                zorder=5,
            )
        i = j


def _mark_shear_zero(ax: Any, xs: np.ndarray, shears: np.ndarray, Lf: float) -> None:
    for j in range(len(xs) - 1):
        v0, v1 = float(shears[j]), float(shears[j + 1])
        if v0 * v1 < 0:
            x0, x1 = float(xs[j]), float(xs[j + 1])
            xz = x0 - v0 * (x1 - x0) / (v1 - v0)
            yr = float(max(np.max(np.abs(shears)), 0.5))
            tick = 0.04 * yr
            ax.plot(
                [xz, xz],
                [-tick, tick],
                color=_BLUE,
                linewidth=0.9,
                alpha=0.65,
                zorder=4,
            )
            ax.text(
                xz,
                tick * 1.8,
                f"x={solver.format_number(xz)}",
                ha="center",
                va="bottom",
                fontsize=_FS_TINY,
                color=_BLUE,
                fontweight="500",
                zorder=7,
            )
            return


def build_beam_figure(
    L: float,
    loads: List[dict],
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_x: float,
    rb_y: float,
    *,
    wide: bool = False,
) -> Any:
    """קורה + N/Q/M — מרווחים: מידות→N (2×d), N→Q (1.5×d), Q→M (1.5×d)."""
    layout = _notebook_layout()
    y_span_beam = layout["y_top"] - layout["y_bottom"]
    xs, normals, shears, moments, crit = _notebook_diagram_series(
        L, loads, ra_pos, rb_pos, ra_x, ra_y, rb_y
    )
    n_bottom = _notebook_diagram_extent_bottom(
        layout["y_n"], normals, _notebook_diagram_scale(normals)
    )
    q_bottom = _notebook_diagram_extent_bottom(
        layout["y_q"], shears, _notebook_diagram_scale(shears)
    )
    m_bottom = _notebook_diagram_extent_bottom(
        layout["y_m"], moments, _notebook_diagram_scale(moments)
    )
    fig_bottom = min(n_bottom, q_bottom, m_bottom, layout["y_fig_bottom"])
    y_span_all = layout["y_top"] - fig_bottom
    fig_h = 2.15 * (y_span_all / y_span_beam)
    _notebook_mpl_rc()
    fig_w = _notebook_fig_width(wide=wide)
    sub_l, sub_r = _subplot_lr(wide=wide)
    fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h), facecolor="none")
    _prep_figure_transparent(fig)
    _prep_axis_on_paper(ax, grid=False)
    _draw_beam_schematic(
        ax, L, loads, ra_pos, rb_pos, ra_x, ra_y, rb_y, set_limits=False
    )
    n_bottom = _draw_n_schematic(ax, L, xs, normals, crit, layout)
    q_bottom = _draw_q_schematic(ax, L, xs, shears, crit, layout)
    m_bottom = _draw_m_schematic(ax, L, xs, moments, crit, layout)
    pad_x = max(0.22, 0.055 * float(L))
    ax.set_xlim(-pad_x, float(L) + pad_x)
    ax.set_ylim(min(n_bottom, q_bottom, m_bottom, layout["y_fig_bottom"]), layout["y_top"])
    fig.subplots_adjust(left=sub_l, right=sub_r, top=0.98, bottom=0.06)
    return fig


def build_beam_schematic_figure(
    L: float,
    loads: List[dict],
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_x: float,
    rb_y: float,
    *,
    wide: bool = False,
) -> Any:
    """קורה + מידות בלבד (ללא דיאגרמות N/Q/M) — לתצוגה זמנית במחברת."""
    _notebook_mpl_rc()
    fig_w = _notebook_fig_width(wide=wide)
    sub_l, sub_r = _subplot_lr(wide=wide)
    fig, ax = plt.subplots(1, 1, figsize=(fig_w, 2.15), facecolor="none")
    _prep_figure_transparent(fig)
    _prep_axis_on_paper(ax, grid=False)
    _draw_beam_schematic(ax, L, loads, ra_pos, rb_pos, ra_x, ra_y, rb_y)
    # חשוב: לא לדרוס set_ylim / set_xlim של _draw_beam_schematic,
    # אחרת קו המידה בין הסמכים והמספר נחתכים.
    fig.subplots_adjust(left=sub_l, right=sub_r, top=0.98, bottom=0.06)
    return fig


def _notebook_graphics_assets(
    *,
    mode: str,
    loads: List[dict],
    L: float,
    ra_pos: float | None = None,
    rb_pos: float | None = None,
    ra_x: float | None = None,
    ra_y: float | None = None,
    rb_x: float | None = None,
    rb_y: float | None = None,
    result: Dict[str, Any] | None = None,
    wide: bool = False,
) -> Tuple[bytes, bytes]:
    """
    מחזיר (png_display, png_download) עבור המחברת:
    - png_display: מה שרואים במסך כרגע (ללא דיאגרמות).
    - png_download: מה שמור להורדה (כולל דיאגרמות).

    כל הלוגיקה הגרפית מרוכזת כאן עבור סמכים + ריתום.
    """
    if mode == "supports":
        if ra_pos is None or rb_pos is None or ra_x is None or ra_y is None or rb_x is None or rb_y is None:
            raise ValueError("supports mode requires ra/rb positions and reactions")
        fig_download = build_beam_figure(
            L, loads, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y, wide=wide
        )
        png_download = _fig_to_png_bytes(fig_download, style="export", pad_inches=0.06)
        plt.close(fig_download)

        fig_display = build_beam_schematic_figure(
            L, loads, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y, wide=wide
        )
        png_display = _fig_to_png_bytes(fig_display, style="embed", pad_inches=0.04)
        plt.close(fig_display)
        return png_display, png_download

    if mode == "cantilever":
        if result is None:
            raise ValueError("cantilever mode requires result dict")
        _notebook_mpl_rc()
        xs = np.asarray(result["xs"], dtype=float)
        normals = np.asarray(result["normal"], dtype=float)
        shears = np.asarray(result["shear"], dtype=float)
        moments = np.asarray(result["moment"], dtype=float)
        fig_w = _notebook_fig_width(wide=wide)
        sub_l, sub_r = _subplot_lr(wide=wide)
        gs_left = sub_l + 0.03 if wide else 0.12

        # download: full page (beam + diagrams)
        fig_download = plt.figure(figsize=(fig_w, 7.2), facecolor="none")
        _prep_figure_transparent(fig_download)
        gs = fig_download.add_gridspec(
            4,
            1,
            height_ratios=[1.05, 1, 1, 1],
            hspace=0.16,
            left=gs_left,
            right=sub_r,
            top=0.98,
            bottom=0.06,
        )
        ax_b = fig_download.add_subplot(gs[0])
        _draw_cantilever_beam_schematic(
            ax_b, L, loads, ra_y=float(result.get("R_Ay", 0.0))
        )
        crit = _cantilever_station_labels(loads, L)
        Lf = float(L)
        x_pad = _beam_x_pad(Lf)
        ax_n = fig_download.add_subplot(gs[1], sharex=ax_b)
        _plot_n_on_beam(ax_n, xs, normals, Lf, x_pad, crit, transparent=True)
        _diagram_titles(fig_download, ax_n, "N(x)", _U_FORCE, _GREEN, Lf=Lf)
        ax_q = fig_download.add_subplot(gs[2], sharex=ax_b)
        _plot_q_on_beam(ax_q, xs, shears, Lf, x_pad, crit, transparent=True)
        _diagram_titles(fig_download, ax_q, "Q(x)", _U_FORCE, _BLUE, Lf=Lf)
        ax_m = fig_download.add_subplot(gs[3], sharex=ax_b)
        _plot_m_on_beam(ax_m, xs, moments, Lf, x_pad, crit, transparent=True)
        _diagram_titles(fig_download, ax_m, "M(x)", _U_MOMENT, _RED, Lf=Lf)

        png_download = _fig_to_png_bytes(fig_download, style="export", pad_inches=0.06)
        plt.close(fig_download)

        # display: beam only (axis top) without diagrams
        fig_display = plt.figure(figsize=(fig_w, 2.15), facecolor="none")
        _prep_figure_transparent(fig_display)
        ax_d = fig_display.add_subplot(1, 1, 1)
        _prep_axis_on_paper(ax_d, grid=False)
        _draw_cantilever_beam_schematic(
            ax_d, L, loads, ra_y=float(result.get("R_Ay", 0.0))
        )
        fig_display.subplots_adjust(left=sub_l, right=sub_r, top=0.98, bottom=0.06)

        png_display = _fig_to_png_bytes(fig_display, style="embed", pad_inches=0.04)
        plt.close(fig_display)
        return png_display, png_download

    raise ValueError(f"unknown notebook graphics mode: {mode}")


def _notebook_graphics_html(png_display: bytes, extra_html: str = "") -> str:
    b64 = base64.b64encode(png_display).decode("ascii")
    return f"""
<div class="nb-row">
  <div class="nb-col-left" style="flex-basis:100%;width:100%;">
    <div class="nb-beam-zone">
      <img src="data:image/png;base64,{b64}" alt="beam notebook graphic"/>
    </div>
    {extra_html}
  </div>
</div>
"""


def _moment_term_string(resultant: float, arm: float) -> str:
    """מחרוזת (|R|·|arm|) עם סימן לפי מומנט."""
    if abs(resultant) < 1e-9 or abs(arm) < 1e-9:
        return ""
    m = -resultant * arm
    body = f"({solver.format_number(abs(resultant))}·{solver.format_number(abs(arm))})"
    return f"+ {body}" if m >= 0 else f"− {body}"


def _reaction_vertical_moment_term(
    reaction_name: str,
    reaction_pos: float,
    ref_pos: float,
) -> str:
    """מומנט מריאקציה אנכית (כלפי מעלה) סביב נקודת הסימון — כמו עומס נקודתי."""
    arm = float(reaction_pos) - float(ref_pos)
    if abs(arm) < 1e-9:
        return ""
    # כוח כלפי מעלה: אותה קונבנציה כמו _moment_term_string(+1, arm)
    m = -arm
    body = f"{reaction_name}·{solver.format_number(abs(arm))}"
    return f"+ {body}" if m >= 0 else f"− {body}"


def _distributed_moment_terms_about(
    w: float, x1: float, x2: float, x_ref: float
) -> List[Tuple[float, str]]:
    """איברי מומנט מעומס מפורס — מפוצל לשניים אם חוצה את נקודת הסימון."""
    out: List[Tuple[float, str]] = []
    xa = float(x1)
    xb = float(x2)
    if xb < xa:
        xa, xb = xb, xa
    span = xb - xa
    if abs(w) < 1e-9 or span <= 1e-9:
        return out
    xref = float(x_ref)
    eps = 1e-9

    def _segment(seg_a: float, seg_b: float) -> None:
        seg_span = seg_b - seg_a
        if seg_span <= eps:
            return
        resultant = w * seg_span
        arm = (seg_a + seg_b) / 2.0 - xref
        term = _moment_term_string(resultant, arm)
        if term:
            out.append((seg_a, term))

    if xa < xref - eps and xb > xref + eps:
        _segment(xa, xref)
        _segment(xref, xb)
    else:
        _segment(xa, xb)
    return out


def _notebook_calc_stub_under_beam(
    loads: List[dict],
    ax_value: float,
    *,
    L: float = 10.0,
    support_mode: str = "supports",
    ra_pos: float = 0.0,
    rb_pos: float = 0.0,
    ra_y: float = 0.0,
    rb_y: float = 0.0,
    cantilever_result: Optional[Dict[str, Any]] = None,
) -> str:
    """בלוק חישובים מינימלי שמופיע מתחת לקורה (סגנון 'מחברת באייפד')."""
    # משוואת ציר X: מתחילים ב-Ax ואז עוברים עומס-עומס משמאל לימין.
    axial_terms: List[Tuple[float, float]] = []  # (x, Fx)
    for ld in loads:
        if ld.get("type") == "point":
            fx = float(ld.get("Fx", 0.0) or 0.0)
            if abs(fx) > 1e-9:
                axial_terms.append((float(ld.get("x", 0.0) or 0.0), fx))
        elif ld.get("type") == "inclined":
            fx = float(ld.get("Fx", 0.0) or 0.0)
            if abs(fx) > 1e-9:
                axial_terms.append((float(ld.get("x", 0.0) or 0.0), fx))
    axial_terms.sort(key=lambda p: p[0])
    has_fx = len(axial_terms) > 0
    if not has_fx:
        ax_eq = f"Ax = 0 {_U_FORCE}"
    else:
        parts: List[str] = ["Ax"]
        for _, fx in axial_terms:
            mag = solver.format_number(abs(fx))
            if fx >= 0:
                parts.append(f"+ {mag}")
            else:
                parts.append(f"− {mag}")
        ax_eq = _join_calc_terms(parts)

    def _fy_term_strings_vertical() -> List[str]:
        """עומסים אנכיים משמאל לימין לפי x (למשוואת ΣFy)."""
        items: List[Tuple[float, float]] = []
        for ld in loads:
            t = ld.get("type")
            if t == "point":
                fy = float(ld.get("Fy", 0.0) or 0.0)
                if abs(fy) > 1e-9:
                    items.append((float(ld.get("x", 0.0) or 0.0), fy))
            elif t == "inclined":
                fy = float(ld.get("Fy", 0.0) or 0.0)
                if abs(fy) > 1e-9:
                    items.append((float(ld.get("x", 0.0) or 0.0), fy))
            elif t == "distributed":
                w = float(ld.get("w", 0.0) or 0.0)
                x1 = float(ld.get("x1", 0.0) or 0.0)
                x2 = float(ld.get("x2", 0.0) or 0.0)
                span = x2 - x1
                if abs(w) < 1e-9 or span <= 1e-9:
                    continue
                items.append(((x1 + x2) / 2.0, w * span))
        items.sort(key=lambda p: p[0])
        out: List[str] = []
        for _, fy in items:
            mag = solver.format_number(abs(fy))
            out.append(f"+ {mag}" if fy >= 0 else f"− {mag}")
        return out

    # ΣM_A = 0 (שורה + שורת פירוק מתחת)
    def _m_term_strings_about(x_ref: float) -> List[str]:
        """מחרוזות (כוח·מרחק) לכל עומס — ממוינות משמאל לימין על הקורה."""
        items: List[Tuple[float, str]] = []
        xref = float(x_ref)
        for ld in loads:
            t = ld.get("type")
            if t == "point":
                fy = float(ld.get("Fy", 0.0) or 0.0)
                x = float(ld.get("x", 0.0) or 0.0)
                dx = x - xref
                if abs(fy) < 1e-9 or abs(dx) < 1e-9:
                    continue
                term = _moment_term_string(fy, dx)
                if term:
                    items.append((x, term))
            elif t == "inclined":
                fy = float(ld.get("Fy", 0.0) or 0.0)
                x = float(ld.get("x", 0.0) or 0.0)
                dx = x - xref
                if abs(fy) < 1e-9 or abs(dx) < 1e-9:
                    continue
                term = _moment_term_string(fy, dx)
                if term:
                    items.append((x, term))
            elif t == "distributed":
                w = float(ld.get("w", 0.0) or 0.0)
                x1 = float(ld.get("x1", 0.0) or 0.0)
                x2 = float(ld.get("x2", 0.0) or 0.0)
                items.extend(_distributed_moment_terms_about(w, x1, x2, xref))
            elif t == "moment":
                mm = float(ld.get("M", 0.0) or 0.0)
                if abs(mm) < 1e-9:
                    continue
                x = float(ld.get("x", 0.0) or 0.0)
                body = f"({solver.format_number(abs(mm))})"
                term = f"+ {body}" if mm >= 0 else f"− {body}"
                items.append((x, term))
        items.sort(key=lambda pair: pair[0])
        return [term for _, term in items]

    if support_mode == "supports" and abs(rb_pos - ra_pos) > 1e-9:
        m_terms_a = _m_term_strings_about(float(ra_pos))
        ma_line = f"{_sym_sigma()}Ma = 0"
        ma_parts = list(m_terms_a) if m_terms_a else ["0"]
        by_term = _reaction_vertical_moment_term("By", float(rb_pos), float(ra_pos))
        if by_term:
            ma_parts.append(by_term)
        ma_calc = _join_calc_terms(ma_parts)
        ma_res_name = "By"
        ma_res_value = float(rb_y)
        ma_res_unit = _U_FORCE
        mb_line = f"{_sym_sigma()}Mb = 0"
        m_terms_b = _m_term_strings_about(float(rb_pos))
        mb_parts = list(m_terms_b) if m_terms_b else ["0"]
        ay_term = _reaction_vertical_moment_term("Ay", float(ra_pos), float(rb_pos))
        if ay_term:
            mb_parts.append(ay_term)
        mb_calc = _join_calc_terms(mb_parts)
        ay_res_name = "Ay"
        ay_res_value = float(ra_y)
        ay_res_unit = _U_FORCE
        ay_header_line = ""
        ay_calc = ""
        fy_header_line = ""
        fy_calc = ""
        mg_line = ""
        mg_calc = ""
    elif support_mode == "cantilever" and cantilever_result is not None:
        Lf = max(float(L), 1e-9)
        m_a = float(cantilever_result.get("M_A", 0.0))
        ay_val = float(cantilever_result.get("R_Ay", 0.0))
        ma_line = ""
        ma_calc = ""
        mb_line = ""
        mb_calc = ""
        fy_terms = _fy_term_strings_vertical()
        # משוואה 2: מומנט בריתום → Ma
        mg_line = f'{_sym_sigma()}M<sub>A</sub> = 0'
        m_terms_a = _m_term_strings_about(0.0)
        mg_parts = ["Ma"]
        if m_terms_a:
            mg_parts.extend(m_terms_a)
        mg_calc = _join_calc_terms(mg_parts)
        ma_res_name = "Ma"
        ma_res_value = m_a
        ma_res_unit = _U_MOMENT
        # משוואה 3: ΣFy — קודם מומנט ב-G עם Ma מהמשוואה הקודמת, אחר כך אימות Fy
        ay_header_line = f"{_sym_sigma()}Fy = 0"
        m_terms_g = _m_term_strings_about(Lf)
        ay_parts = [str(solver.format_number(m_a)), f"Ay·{solver.format_number(Lf)}"]
        if m_terms_g:
            ay_parts.extend(m_terms_g)
        ay_calc = _join_calc_terms(ay_parts)
        ay_res_name = "Ay"
        ay_res_value = ay_val
        ay_res_unit = _U_FORCE
        fy_header_line = ""
        fy_calc_parts = [solver.format_number(ay_val)]
        if fy_terms:
            fy_calc_parts.extend(fy_terms)
        fy_calc = _join_calc_terms(fy_calc_parts)
    else:
        ma_line = f"{_sym_sigma()}Ma = 0"
        ma_calc = ""
        ma_res_name = ""
        ma_res_value = 0.0
        ma_res_unit = ""
        mb_line = ""
        mb_calc = ""
        ay_res_name = ""
        ay_res_value = 0.0
        ay_res_unit = ""
        ay_header_line = ""
        ay_calc = ""
        fy_header_line = ""
        fy_calc = ""
        mg_line = ""
        mg_calc = ""

    calc_rows: List[str] = [
        _reaction_sigma_group_html(
            f"{_sym_sigma()}Fx = 0",
            ax_eq,
            "Ax",
            float(ax_value),
            _U_FORCE,
        )
    ]
    if support_mode == "cantilever" and cantilever_result is not None:
        if mg_calc:
            calc_rows.append(
                _reaction_sigma_group_html(
                    mg_line,
                    mg_calc,
                    ma_res_name,
                    ma_res_value,
                    ma_res_unit,
                )
            )
        if ay_calc:
            calc_rows.append(
                _reaction_sigma_group_html(
                    ay_header_line,
                    ay_calc,
                    ay_res_name,
                    ay_res_value,
                    ay_res_unit,
                )
            )
    else:
        if ma_calc:
            calc_rows.append(
                _reaction_sigma_group_html(
                    ma_line,
                    ma_calc,
                    ma_res_name,
                    ma_res_value,
                    ma_res_unit,
                )
            )
        if support_mode == "supports" and mb_calc:
            calc_rows.append(
                _reaction_sigma_group_html(
                    mb_line,
                    mb_calc,
                    ay_res_name,
                    ay_res_value,
                    ay_res_unit,
                )
            )

    return "\n".join(
        [
            '<div style="width:100%;display:flex;justify-content:flex-start;">',
            f'<div class="nb-calc-block" style="width:100%;flex:0 0 auto;max-width:100%;margin-top:{_BEAM_TO_CALC_GAP_MM}mm;direction:ltr;text-align:left;unicode-bidi:plaintext;padding:0 6px 0 {_REACTION_CALC_INDENT};">',
            '<div style="margin:0;padding:0;min-width:min-content;">',
            *calc_rows,
            "</div>",
            "</div>",
            "</div>",
        ]
    )


def build_forces_figure(
    L: float,
    loads: List[dict],
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_x: float,
    rb_y: float,
    *,
    wide: bool = False,
) -> Any:
    """דיאגרמות N, Q, M — תמונה משולבת (הורדה / תאימות לאחור)."""
    positions = solver.critical_x_positions(loads, L, ra_pos, rb_pos)
    xs = solver.beam_plot_x_coords(L, positions)
    moments = np.array([solver.bending_moment(x, loads, ra_y, rb_y, ra_pos, rb_pos) for x in xs])
    shears = np.array([solver.shear_force(x, loads, ra_y, rb_y, ra_pos, rb_pos) for x in xs])
    normals = np.array([solver.normal_force(x, loads, ra_x, ra_pos) for x in xs])
    Lf = float(L)
    crit = station_labels(loads, L, ra_pos, rb_pos)
    return _build_combined_forces_figure(
        xs, normals, shears, moments, Lf, crit, wide=wide
    )


def _build_combined_forces_figure(
    xs: np.ndarray,
    normals: np.ndarray,
    shears: np.ndarray,
    moments: np.ndarray,
    Lf: float,
    crit: List[Tuple[float, str]],
    *,
    wide: bool = False,
) -> Any:
    _notebook_mpl_rc()
    fig_w = _notebook_fig_width(wide=wide)
    sub_l, sub_r = _subplot_lr(wide=wide)
    q_gap_in = _grid_gap_mm(_Q_DIAGRAM_SHIFT_SQUARES) / 25.4
    m_gap_in = _grid_gap_mm(_M_DIAGRAM_SHIFT_SQUARES) / 25.4
    h_ratios = [
        _FORCES_PANEL_H_IN,
        max(0.001, q_gap_in),
        _FORCES_PANEL_H_IN,
        max(0.001, m_gap_in),
        _FORCES_PANEL_H_IN,
    ]
    fig_h = sum(h_ratios)
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor="none")
    _prep_figure_transparent(fig)
    gs = fig.add_gridspec(
        5, 1, height_ratios=h_ratios, hspace=0.04,
        left=sub_l, right=sub_r, top=0.98, bottom=0.08,
    )
    x_pad = 0.0
    ax_n = fig.add_subplot(gs[0])
    _plot_n_on_beam_clean(ax_n, xs, normals, Lf, x_pad, crit, transparent=True)
    _diagram_titles(fig, ax_n, "N(x)", _U_FORCE, _GREEN, Lf=Lf)
    ax_v = fig.add_subplot(gs[2], sharex=ax_n)
    _plot_q_on_beam_clean(ax_v, xs, shears, Lf, x_pad, crit, transparent=True)
    _diagram_titles(fig, ax_v, "Q(x)", _U_FORCE, _BLUE, Lf=Lf)
    ax_m = fig.add_subplot(gs[4], sharex=ax_n)
    _plot_m_on_beam_clean(ax_m, xs, moments, Lf, x_pad, crit, transparent=True)
    _diagram_titles(fig, ax_m, "M(x)", _U_MOMENT, _RED, Lf=Lf)
    return fig


def _relax_diagram_artists_clip(ax: Any) -> None:
    """אל תחתוך קווים/מילוי בגבול הציר — רלוונטי כשהגרף מתוח (mult < 1)."""
    for artist in (*ax.lines, *ax.collections, *ax.patches):
        artist.set_clip_on(False)
    ax.set_clip_on(False)


def _expand_force_panel_limits(ax: Any, Lf: float, x_pad: float) -> None:
    """מרווח אופקי קטן בלבד — לא מרחיב y (שומר על מתיחת mult)."""
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    xspan = max(xmax - xmin, 1e-9)
    xmin_pad = max(xspan * 0.04, _beam_x_pad(Lf) * 0.25)
    ax.set_xlim(xmin - xmin_pad, xmax + xmin_pad)
    ax.set_ylim(ymin, ymax)


def _force_panel_subplot_margins(*, wide: bool) -> tuple[float, float, float, float]:
    """שולי figure לפאנל N/Q/M."""
    sub_l, sub_r = _subplot_lr(wide=wide)
    left = max(sub_l, 0.075)
    return left, sub_r, 0.93, 0.09


def _build_force_panel_figure(
    xs: np.ndarray,
    values: np.ndarray,
    Lf: float,
    x_pad: float,
    crit: List[Tuple[float, str]],
    plot_fn: Any,
    title: str,
    unit: str,
    color: str,
    *,
    wide: bool = False,
    panel_h_in: Optional[float] = None,
) -> Any:
    _notebook_mpl_rc()
    fig_w = _notebook_fig_width(wide=wide)
    fig_h = panel_h_in if panel_h_in is not None else _FORCES_PANEL_H_IN
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor="none")
    _prep_figure_transparent(fig)
    ax = fig.add_subplot(111)
    sub_l, sub_r, sub_t, sub_b = _force_panel_subplot_margins(wide=wide)
    fig.subplots_adjust(left=sub_l, right=sub_r, top=sub_t, bottom=sub_b)
    plot_fn(ax, xs, values, Lf, x_pad, crit, transparent=True)
    _expand_force_panel_limits(ax, Lf, x_pad)
    _relax_diagram_artists_clip(ax)
    _diagram_titles(fig, ax, title, unit, color, Lf=Lf)
    return fig


def _forces_diagram_html(
    png_n: bytes,
    png_q: bytes,
    png_m: bytes,
    layout: NotebookPdfLayout,
) -> str:
    from notebook.html.forces import _forces_diagram_html as _impl

    return _impl(png_n, png_q, png_m, layout)


def _build_forces_diagram_html(
    xs: np.ndarray,
    normals: np.ndarray,
    shears: np.ndarray,
    moments: np.ndarray,
    Lf: float,
    crit: List[Tuple[float, str]],
    *,
    wide: bool = False,
    layout: Optional[NotebookPdfLayout] = None,
) -> str:
    from notebook.html.forces import _build_forces_diagram_html as _impl

    return _impl(
        xs,
        normals,
        shears,
        moments,
        Lf,
        crit,
        wide=wide,
        layout=layout,
        build_force_panel_figure=_build_force_panel_figure,
        plot_n_clean=_plot_n_on_beam_clean,
        plot_q_clean=_plot_q_on_beam_clean,
        plot_m_clean=_plot_m_on_beam_clean,
        prep_figure_notebook_paper=_prep_figure_notebook_paper,
    )


def build_cantilever_forces_figure(
    loads: List[dict], L: float, result: Dict[str, Any], *, wide: bool = False
) -> Any:
    """דיאגרמות N, Q, M לזיז — תמונה משולבת (תאימות לאחור)."""
    xs = np.asarray(result["xs"], dtype=float)
    normals = np.asarray(result["normal"], dtype=float)
    shears = np.asarray(result["shear"], dtype=float)
    moments = np.asarray(result["moment"], dtype=float)
    Lf = float(L)
    crit = _cantilever_station_labels(loads, L)
    return _build_combined_forces_figure(
        xs, normals, shears, moments, Lf, crit, wide=wide
    )


def build_diagram_figure(
    L: float,
    loads: List[dict],
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_x: float,
    rb_y: float,
) -> Any:
    from notebook.legacy import build_diagram_figure as _impl

    return _impl(
        L,
        loads,
        ra_pos,
        rb_pos,
        ra_x,
        ra_y,
        rb_x,
        rb_y,
        notebook_mpl_rc=_notebook_mpl_rc,
        draw_beam_schematic=_draw_beam_schematic,
        beam_x_pad=_beam_x_pad,
        station_labels_fn=station_labels,
        plot_n_on_beam=_plot_n_on_beam,
        plot_q_on_beam=_plot_q_on_beam,
        plot_m_on_beam=_plot_m_on_beam,
        diagram_titles=_diagram_titles,
    )


def _build_moment_panel_html(rows: List[Dict[str, Any]], loads: List[dict], L: float,
                             ra_pos: float, rb_pos: float, ra_y: float, rb_y: float) -> str:
    """רשימת מומנטים אדומה מתחת לדיאגרמות — כמו בתחתית השמאל בתמונה."""
    lines: List[str] = [
        '<div class="nb-m-panel">',
        "<h5>חישוב מומנטים בנקודות</h5>",
    ]
    stations = [(r["x"], r["label"], r["M"]) for r in rows]
    for x, lab, m_val in stations:
        lines.append(
            f'<p class="nb-line nb-red">M_{lab} = {solver.format_number(m_val)} {_U_MOMENT}</p>'
        )
    lines.append("</div>")
    return "\n".join(lines)


def _nb_line(text: str, css: str = "nb-black") -> str:
    from notebook.html.primitives import _nb_line as _impl

    return _impl(text, css=css)


def _esc_num(value: float) -> str:
    from notebook.html.primitives import _esc_num as _impl

    return _impl(value)


def _sym_sigma() -> str:
    from notebook.html.primitives import _sym_sigma as _impl

    return _impl()


def _sym_delta() -> str:
    from notebook.html.primitives import _sym_delta as _impl

    return _impl()


def _nb_step(text: str, css: str = "nb-eq") -> str:
    from notebook.html.primitives import _nb_step as _impl

    return _impl(text, css=css)


def _nb_step_html(inner_html: str, css: str = "nb-eq") -> str:
    from notebook.html.primitives import _nb_step_html as _impl

    return _impl(inner_html, css=css)


def _nb_step_html_style(inner_html: str, css: str = "nb-eq", style: str = "") -> str:
    from notebook.html.primitives import _nb_step_html_style as _impl

    return _impl(inner_html, css=css, style=style)


def _nb_calc_eq_row(inner_html: str, line_style: str = "", *, oneline: bool = True) -> str:
    from notebook.html.primitives import _nb_calc_eq_row as _impl

    return _impl(inner_html, line_style=line_style, oneline=oneline)


def _nb_calc_answer_row(inner_html: str, line_style: str = "") -> str:
    from notebook.html.primitives import _nb_calc_answer_row as _impl

    return _impl(inner_html, line_style=line_style)


def _calc_term_body_sign(term: str) -> Tuple[int, str]:
    from notebook.html.math_format import _calc_term_body_sign as _impl

    return _impl(term)


def _join_calc_terms(parts: List[str]) -> str:
    from notebook.html.math_format import _join_calc_terms as _impl

    return _impl(parts)


def _join_eq_value_lines_minus_only(lines: List[str], total: float) -> str:
    from notebook.html.math_format import _join_eq_value_lines_minus_only as _impl

    return _impl(lines, total)


def _reaction_answer_css_class(ans_name: str) -> str:
    """צבע מסגרת תשובה: Ax ירוק, Ay/By כחול, מומנט אדום."""
    key = str(ans_name or "").strip().replace("_", "").lower()
    if key in ("ax", "rax"):
        return "nb-ans-ax"
    if key in ("ay", "by", "ray", "rby"):
        return "nb-ans-ay"
    if key in ("ma", "mb") or (len(key) >= 2 and key[0] == "m"):
        return "nb-ans-m"
    return "nb-ans-ax"


def _reaction_answer_inline_style(ans_name: str) -> str:
    """סגנון inline — מסגרת צמודה לטקסט התשובה בלבד."""
    css = _reaction_answer_css_class(ans_name)
    base = (
        "display:inline;padding:0 5px;border-radius:3px;"
        f"font-weight:600;line-height:1.25;color:{_CHARCOAL};"
    )
    if css == "nb-ans-ay":
        return f"{base}background:#e8f0fa;border:1pt solid {_BLUE};"
    if css == "nb-ans-m":
        return f"{base}background:#faecea;border:1pt solid {_RED};"
    return f"{base}background:#e8f3ec;border:1pt solid {_GREEN};"


def _sigma_rx_after_colon_spaces(sigma_html: str) -> int:
    """רווחים אחרי ':' — 8 ל-ΣFx/ΣFy, 6 ל-ΣMa/ΣMb וכו'."""
    plain = re.sub(r"<[^>]+>", "", sigma_html)
    if re.search(r"Σ\s*F", plain):
        return _REACTION_SIGMA_AFTER_COLON_SPACES_F
    return _REACTION_SIGMA_AFTER_COLON_SPACES


def _sigma_rx_gap_html(sigma_html: str) -> str:
    return "&nbsp;" * _sigma_rx_after_colon_spaces(sigma_html)


def _sigma_rx_prefix_html(sigma_html: str, *, hide: bool = False) -> str:
    """Σ=0: + רווחים — prefix משותף לשורת משוואה וליישור תשובה."""
    hide_cls = " nb-rx-prefix-hide" if hide else ""
    return (
        f'<span class="nb-rx-prefix{hide_cls}">{sigma_html}:</span>'
        f"{_sigma_rx_gap_html(sigma_html)}"
    )


def _parse_calc_display_number(text: str) -> float:
    from notebook.html.math_format import _parse_calc_display_number as _impl

    return _impl(text)


def _expand_parenthetical_inner(inner: str) -> str:
    from notebook.html.math_format import _expand_parenthetical_inner as _impl

    return _impl(inner)


def _expand_calc_parentheses(eq_text: str) -> str:
    from notebook.html.math_format import _expand_calc_parentheses as _impl

    return _impl(eq_text)


def _reaction_sigma_group_html(
    sigma_html: str,
    eq_text: str,
    ans_name: str,
    ans_value: float,
    ans_unit: str,
) -> str:
    """Σ=0: פירוק באותה שורה; תשובת ריאקציה בשורה מתחת מיושרת לפירוק."""
    prefix = _sigma_rx_prefix_html(sigma_html)
    if _eq_already_shows_answer(eq_text, ans_name, ans_value, ans_unit):
        ans_body = _reaction_answer_box_html(ans_name, ans_value, ans_unit)
        return (
            '<table class="nb-rx-table">'
            f'<tr><td class="nb-rx-line">{prefix}<span class="nb-rx-body">'
            f"{ans_body}</span></td></tr></table>"
        )
    eq_html = html_lib.escape(_clean_math_text(str(eq_text).strip()))
    eq_body = (
        f'<span class="nb-rx-eq-text">{eq_html}</span>'
        f'<span class="nb-eq-tail"> = 0</span>'
    )
    ans_body = _reaction_answer_box_html(ans_name, ans_value, ans_unit)
    prefix_hide = _sigma_rx_prefix_html(sigma_html, hide=True)
    expand_row = ""
    if "(" in eq_text:
        expanded = _expand_calc_parentheses(eq_text)
        if expanded.strip() != _clean_math_text(str(eq_text).strip()):
            expand_html = html_lib.escape(expanded)
            expand_body = (
                f'<span class="nb-rx-expand-text">{expand_html}</span>'
                f'<span class="nb-eq-tail"> = 0</span>'
            )
            expand_row = (
                f'<tr class="nb-rx-expand-row"><td class="nb-rx-line">{prefix_hide}'
                f'<span class="nb-rx-body">{expand_body}</span></td></tr>'
            )
    return (
        '<table class="nb-rx-table">'
        f'<tr class="nb-rx-eq-row"><td class="nb-rx-line">{prefix}<span class="nb-rx-body">'
        f"{eq_body}</span></td></tr>"
        f"{expand_row}"
        f'<tr class="nb-rx-ans-row"><td class="nb-rx-line">{prefix_hide}'
        f'<span class="nb-rx-body">{ans_body}</span></td></tr>'
        f"</table>"
    )


def _reaction_answer_text(ans_name: str, ans_value: float, ans_unit: str) -> str:
    return _clean_math_text(
        f"{ans_name} = {solver.format_number(ans_value)} {ans_unit}".strip()
    )


def _eq_already_shows_answer(
    eq_text: str, ans_name: str, ans_value: float, ans_unit: str
) -> bool:
    """המשוואה כבר מציגה את התשובה — בלי צורך בשורת תוצאה נוספת."""
    eq_clean = _clean_math_text(str(eq_text or "").strip())
    if not eq_clean:
        return False
    ans_txt = _reaction_answer_text(ans_name, ans_value, ans_unit)
    if eq_clean == ans_txt:
        return True
    ans_no_unit = _clean_math_text(
        f"{ans_name} = {solver.format_number(ans_value)}"
    )
    return eq_clean == ans_no_unit


def _reaction_answer_box_html(ans_name: str, ans_value: float, ans_unit: str) -> str:
    ans_txt = _reaction_answer_text(ans_name, ans_value, ans_unit)
    css = _reaction_answer_css_class(ans_name)
    style = _reaction_answer_inline_style(ans_name)
    return (
        f'<span class="nb-box nb-box-answer {css}" style="{style}">'
        f"{html_lib.escape(ans_txt)}</span>"
    )


def _format_reaction_calc_inner(
    eq_text: str, ans_name: str, ans_value: float, ans_unit: str
) -> str:
    """שורת חישוב: משוואה + תוצאה, או תוצאה בלבד אם כבר טריוויאלית."""
    ans_html = _reaction_answer_box_html(ans_name, ans_value, ans_unit)
    if _eq_already_shows_answer(eq_text, ans_name, ans_value, ans_unit):
        return ans_html
    eq_html = html_lib.escape(_clean_math_text(str(eq_text).strip()))
    return f"{eq_html}{_nb_eq_answer_tail(ans_name, ans_value, ans_unit)}"


def _nb_eq_zero_tail() -> str:
    """'= 0' בסוף משוואה — לא נשבר לשורה נפרדת."""
    return '<span class="nb-eq-tail"> = 0</span>'


def _nb_eq_answer_tail(ans_name: str, ans_value: float, ans_unit: str) -> str:
    """'= 0' + פסיק + תשובה — נשארים באותה שורה אחרי המשוואה."""
    ans_html = _reaction_answer_box_html(ans_name, ans_value, ans_unit)
    return f'<span class="nb-eq-tail"> = 0&nbsp;&nbsp;&nbsp;{ans_html}</span>'


def _nb_answer_box(inner_html: str, *, ans_name: str = "") -> str:
    css = _reaction_answer_css_class(ans_name) if ans_name else ""
    extra = f" {css}" if css else ""
    style_attr = (
        f' style="{_reaction_answer_inline_style(ans_name)}"' if ans_name else ""
    )
    return (
        f'<p class="nb-line nb-eq">'
        f'<span class="nb-box nb-box-answer{extra}"{style_attr}>{inner_html}</span>'
        f"</p>"
    )


def _shear_zero_card_html(
    loads: List[dict],
    L: float,
    ra_pos: float,
    rb_pos: float,
    ra_y: float,
    rb_y: float,
) -> str:
    """כרטיס תחתון: X = Q/q = … (מיקום מומנט מקסימלי תחת מפולג)."""
    eps = 1e-6
    for i, ld in enumerate(loads, 1):
        if ld["type"] != "distributed":
            continue
        x1, x2, w = float(ld["x1"]), float(ld["x2"]), float(ld["w"])
        if abs(w) < 1e-9 or x2 - x1 < 1e-9:
            continue
        v_start = solver.shear_force(x1 + eps, loads, ra_y, rb_y, ra_pos, rb_pos)
        q_mag = abs(w)
        v_abs = abs(v_start)
        if abs(v_start) < 1e-9:
            xz = x1
        else:
            xz = x1 - v_start / w
        if x1 - 0.01 <= xz <= x2 + 0.01:
            return (
                '<div class="nb-xzero-card">'
                '<p class="nb-xzero-title">מיקום מומנט מקסימלי — Q = 0</p>'
                f'<p class="nb-line nb-moment">X = Q/q = '
                f"{html_lib.escape(str(solver.format_number(v_abs)))}/"
                f"{html_lib.escape(str(solver.format_number(q_mag)))} = "
                f"{html_lib.escape(str(solver.format_number(xz)))} m</p>"
                "</div>"
            )
    return ""


def _moment_handwriting_note() -> str:
    return _nb_step(
        "חישוב מהלך שרטוט מומנט: גזירה חיובית (למטה) → מומנט מתעקל כלפי מטה; "
        "בנקודה שבה Q = 0 המומנט שואף למקסימום.",
        "nb-note",
    )


def _build_calc_html(
    loads: List[dict],
    L: float,
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_x: float,
    rb_y: float,
) -> str:
    from notebook.legacy import build_calc_html as _impl

    return _impl(
        loads,
        L,
        ra_pos,
        rb_pos,
        ra_x,
        ra_y,
        rb_x,
        rb_y,
        equilibrium_sections_fn=_equilibrium_sections,
        values_at_stations_fn=_values_at_stations,
        nb_step_html_fn=_nb_step_html,
        sym_sigma_fn=_sym_sigma,
        join_eq_value_lines_minus_only_fn=_join_eq_value_lines_minus_only,
        nb_step_fn=_nb_step,
        esc_num_fn=_esc_num,
        nb_answer_box_fn=_nb_answer_box,
        sym_delta_fn=_sym_delta,
        moment_handwriting_note_fn=_moment_handwriting_note,
        shear_zero_card_html_fn=_shear_zero_card_html,
        shear_zero_notes_fn=_shear_zero_notes,
    )


def _fig_to_png_bytes(
    fig: Any,
    *,
    style: str = "embed",
    pad_inches: float = 0.02,
    bbox: str = "tight",
) -> bytes:
    from notebook.export.png import _fig_to_png_bytes as _impl

    return _impl(
        fig,
        prep_figure_notebook_paper=_prep_figure_notebook_paper,
        style=style,
        pad_inches=pad_inches,
        bbox=bbox,
    )


def build_page_html(
    loads: List[dict],
    L: float,
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_x: float,
    rb_y: float,
    *,
    wide_layout: bool = False,
    pdf_layout: Optional[NotebookPdfLayout] = None,
) -> Tuple[str, bytes, bytes]:
    from notebook.assemble.page import build_page_html as _impl

    return _impl(
        loads,
        L,
        ra_pos,
        rb_pos,
        ra_x,
        ra_y,
        rb_x,
        rb_y,
        wide_layout=wide_layout,
        pdf_layout=pdf_layout,
        notebook_graphics_assets_fn=_notebook_graphics_assets,
        station_labels_fn=station_labels,
        build_forces_diagram_html_fn=_build_forces_diagram_html,
        values_at_stations_fn=_values_at_stations,
        point_calc_grid_html_fn=_point_calc_grid_html,
        notebook_calc_stub_under_beam_fn=_notebook_calc_stub_under_beam,
        build_bot_notebook_extra_html_fn=build_bot_notebook_extra_html,
        notebook_graphics_html_fn=_notebook_graphics_html,
        wrap_pdf_document_fn=_wrap_pdf_document,
        html_to_pdf_bytes_fn=_html_to_pdf_bytes,
        pdf_to_png_bytes_fn=_pdf_to_png_bytes,
        wrap_iframe_document_fn=_wrap_iframe_document,
        export_dpi=_EXPORT_DPI,
    )


def _extract_notebook_body(page_html: str) -> str:
    marker = '<article class="nb-page">'
    if marker in page_html:
        return page_html.split(marker, 1)[1].split("</article>", 1)[0]
    return page_html


def build_page_pdf_from_html(page_html: str) -> bytes:
    """PDF מדף HTML שכבר נבנה (בלי לחשב שרטוטים פעמיים)."""
    return _html_to_pdf_bytes(_wrap_pdf_document(_extract_notebook_body(page_html)))


def build_page_pdf(
    loads: List[dict],
    L: float,
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_x: float,
    rb_y: float,
) -> bytes:
    """PDF של דף המחברת המלא (כמו בתצוגה)."""
    _, _, pdf_bytes = build_page_html(
        loads, L, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y
    )
    return pdf_bytes


def build_cantilever_page_pdf_from_html(page_html: str) -> bytes:
    return _html_to_pdf_bytes(_wrap_pdf_document(_extract_notebook_body(page_html)))


def build_cantilever_page_pdf(loads: List[dict], L: float, result: Dict[str, Any]) -> bytes:
    _, _, pdf_bytes = build_cantilever_page_html(loads, L, result)
    return pdf_bytes


def _load_live_notebook_module():
    """טוען beam_notebook מחדש מהדיסק — עוקף מטמון מודול ישן של Streamlit."""
    import importlib.util

    path = Path(__file__).resolve()
    name = "beam_notebook_live"
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    else:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        spec.loader.exec_module(mod)
    return mod


def render_solved_notebook(
    loads: List[dict],
    L: float,
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_x: float,
    rb_y: float,
) -> None:
    import streamlit as st
    import streamlit.components.v1 as components

    if not loads:
        st.info("הוסף עומסים על הקורה (בסרגל או בלוח) כדי לראות כאן תרגיל פתור במחברת.")
        st.caption("אם העומסים כבר מופיעים בלוח — לחץ **Apply changes** כדי לשמור אותם לחישוב ולמחברת.")
        return
    nb = _load_live_notebook_module()
    nb_path = Path(nb.__file__).resolve()
    st.caption(f"דף **A4** (חצי־חצי) · קובץ: `{nb_path.name}`")
    try:
        page_html, png_bytes, pdf_bytes = nb.build_page_html(
            loads, L, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y
        )
    except Exception as exc:
        st.error(f"שגיאה בבניית דף המחברת: {exc}")
        return
    try:
        st.html(page_html, width="stretch")
    except Exception:
        components.html(page_html, height=_A4_IFRAME_HEIGHT_PX, scrolling=False)
    d1, d2 = st.columns(2)
    with d1:
        if st.download_button(
            "הורדת פתרון מחברת (PDF)",
            data=pdf_bytes,
            file_name="beam-solved-notebook.pdf",
            mime="application/pdf",
            type="primary",
            key="notebook_pdf_download",
        ):
            from beam_ui import track_ga_event

            track_ga_event("pdf_downloaded")
    with d2:
        st.download_button(
            "הורדת פתרון מחברת (PNG)",
            data=png_bytes,
            file_name="beam-solved-notebook.png",
            mime="image/png",
            key="notebook_png_download",
        )


def _cantilever_station_labels(loads: List[dict], L: float) -> List[Tuple[float, str]]:
    xs = solver.critical_x_positions(loads, L, 0.0, L)
    labels: Dict[float, str] = {0.0: "A", round(float(L), 6): "G"}
    letters = "BCDEFHIJKLMNOPQRSTUVWXYZ"
    li = 0
    for x in xs:
        k = round(float(x), 6)
        if k not in labels:
            labels[k] = letters[li] if li < len(letters) else f"P{li}"
            li += 1
    return [(x, labels[round(float(x), 6)]) for x in xs]


def build_cantilever_page_html(
    loads: List[dict], L: float, result: Dict[str, Any], *, wide_layout: bool = False,
    pdf_layout: Optional[NotebookPdfLayout] = None,
) -> Tuple[str, bytes, bytes]:
    from notebook.assemble.cantilever import build_cantilever_page_html as _impl

    return _impl(
        loads,
        L,
        result,
        wide_layout=wide_layout,
        pdf_layout=pdf_layout,
        notebook_graphics_assets_fn=_notebook_graphics_assets,
        cantilever_station_labels_fn=_cantilever_station_labels,
        build_forces_diagram_html_fn=_build_forces_diagram_html,
        cantilever_values_at_stations_fn=_cantilever_values_at_stations,
        point_calc_grid_html_fn=_point_calc_grid_html,
        notebook_calc_stub_under_beam_fn=_notebook_calc_stub_under_beam,
        build_bot_notebook_extra_html_fn=build_bot_notebook_extra_html,
        notebook_graphics_html_fn=_notebook_graphics_html,
        wrap_pdf_document_fn=_wrap_pdf_document,
        html_to_pdf_bytes_fn=_html_to_pdf_bytes,
        pdf_to_png_bytes_fn=_pdf_to_png_bytes,
        wrap_iframe_document_fn=_wrap_iframe_document,
        export_dpi=_EXPORT_DPI,
    )


def render_cantilever_notebook(loads: List[dict], L: float, result: Dict[str, Any]) -> None:
    import streamlit as st
    import streamlit.components.v1 as components

    if not loads:
        st.info("הוסף עומסים על הקורה כדי לראות כאן תרגיל זיז פתור במחברת.")
        return
    nb = _load_live_notebook_module()
    nb_path = Path(nb.__file__).resolve()
    st.caption(f"דף **A4** (חצי־חצי) · קובץ: `{nb_path.name}`")
    try:
        page_html, png_bytes, pdf_bytes = nb.build_cantilever_page_html(loads, L, result)
    except Exception as exc:
        st.error(f"שגיאה בבניית דף המחברת: {exc}")
        return
    try:
        st.html(page_html, width="stretch")
    except Exception:
        components.html(page_html, height=_A4_IFRAME_HEIGHT_PX, scrolling=False)
    d1, d2 = st.columns(2)
    with d1:
        if st.download_button(
            "הורדת פתרון זיז (PDF)",
            data=pdf_bytes,
            file_name="beam-cantilever-solved-notebook.pdf",
            mime="application/pdf",
            type="primary",
            key="cantilever_notebook_pdf_download",
        ):
            from beam_ui import track_ga_event

            track_ga_event("pdf_downloaded")
    with d2:
        st.download_button(
            "הורדת פתרון זיז (PNG)",
            data=png_bytes,
            file_name="beam-cantilever-solved-notebook.png",
            mime="image/png",
            key="cantilever_notebook_png_download",
        )
