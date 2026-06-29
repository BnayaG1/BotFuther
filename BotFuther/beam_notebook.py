# -*- coding: utf-8 -*-
"""תצוגת דף מחברת — מבוסס על תרגיל פתור ידני (שרטוט + דיאגרמות + חישובים)."""
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

import matplotlib.pyplot as plt
from matplotlib.patches import Arc, Polygon
import numpy as np
from matplotlib.lines import Line2D
import streamlit as st
import streamlit.components.v1 as components

import solver

# צבעי «דיו» כמו בתמונת הדוגמה
_INK = "#1a1a1b"
_GREEN = "#188038"
_BLUE = "#0056b3"
_RED = "#d93025"
_PAPER = "#fdf5e6"
_GRID = "#c8c0b0"
_EXPORT_DPI = 300
_EMBED_DPI = 150
_BOT_EXPORT_DPI = 150
_BEAM_MAIN_LW = 2.2
_HEADER = "#1e3a5f"
_CHARCOAL = "#2c3e50"
_HIGHLIGHT_ANSWER = "#e2f0d9"
_HIGHLIGHT_ANSWER_BORDER = "#8fad7a"
_ORANGE_NOTE = "#c2410c"
_BRIGHT_GREEN = "#16a34a"
# משבצת אחת בנייר (11px) — בקואורדינטות שרטוט הקורה
_NOTEBOOK_GRID_Y = 0.11
_U_FORCE = "t"
_U_MOMENT = "tm"
_UI_FONT_CSS = "'Rubik', 'Heebo', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"
_FONT_DIR = Path(__file__).resolve().parent / ".notebook_fonts"
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

# A4 (210×297 mm) — גובה iframe בפיקסלים (~96 DPI)
_A4_IFRAME_HEIGHT_PX = 1160


_NOTEBOOK_IFRAME_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600&family=Heebo:wght@400;500;600&display=swap');
* {{ box-sizing: border-box; }}
html, body {{
  margin: 0; padding: 0;
  background: #2e2820;
  font-family: {_UI_FONT_CSS};
}}
.nb-outer {{
  display: flex;
  justify-content: center;
  padding: 8px;
}}
.nb-page {{
  width: 210mm;
  height: 297mm;
  max-width: calc(100vw - 24px);
  max-height: 297mm;
  padding: 6mm 7mm 7mm;
  color: {_INK};
  background-color: {_PAPER};
  background-image:
    linear-gradient({_GRID} 1px, transparent 1px),
    linear-gradient(90deg, {_GRID} 1px, transparent 1px);
  background-size: 11px 11px;
  border: 1px solid rgba(90, 70, 40, 0.4);
  box-shadow: 0 10px 28px rgba(0,0,0,0.28);
  overflow: hidden;
  font-family: {_UI_FONT_CSS};
}}
.nb-page *:not(img) {{
  font-family: {_UI_FONT_CSS};
  font-weight: 400;
}}
.nb-row {{
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: stretch;
  gap: 6px;
  width: 100%;
  height: calc(297mm - 14mm);
  max-height: calc(297mm - 14mm);
  direction: ltr;
}}
.nb-col-left {{
  flex: 0 0 50%;
  width: 50%;
  min-width: 0;
  height: 100%;
  max-height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: transparent;
}}
.nb-beam-zone {{
  flex: 0 0 auto;
  min-height: 0;
  height: auto;
  width: 100%;
  overflow: hidden;
  background: transparent;
}}
.nb-beam-zone img {{
  width: calc(100% + 22px);
  height: auto;
  object-fit: contain;
  object-position: left top;
  margin-left: -22px;
  transform: scale(0.8) translateX(99px);
  transform-origin: left top;
  display: block;
  background: transparent;
}}
.nb-col-calc {{
  flex: 0 0 50%;
  width: 50%;
  min-width: 0;
  height: 100%;
  max-height: 100%;
  overflow-x: hidden;
  overflow-y: auto;
  direction: rtl;
  unicode-bidi: plaintext;
  text-align: right;
  font-family: {_UI_FONT_CSS};
  font-size: 10.5pt;
  line-height: 2.15;
  letter-spacing: 0.02em;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  font-variant-numeric: tabular-nums;
  padding: 10px 14px 14px 18px;
  border-left: none;
  align-self: stretch;
  background: transparent;
}}
.nb-flow {{
  display: flex;
  flex-direction: column;
  gap: 0;
  min-height: 100%;
}}
.nb-block {{
  margin-bottom: 22px;
  padding: 0 2px;
}}
.nb-block:last-child {{
  margin-bottom: 0;
}}
.nb-calc-title {{
  margin: 0 0 18px 0;
  padding: 0 0 8px 0;
  font-size: 14pt;
  font-weight: 700;
  color: {_HEADER};
  border-bottom: 2px solid rgba(30, 58, 95, 0.2);
  line-height: 1.4;
  letter-spacing: -0.02em;
}}
.nb-block-label {{
  margin: 20px 0 12px 0;
  font-size: 11pt;
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: 1.5;
}}
.nb-block-label.nb-lbl-green {{ color: {_BRIGHT_GREEN}; }}
.nb-block-label.nb-lbl-blue {{ color: {_BLUE}; }}
.nb-block-label.nb-lbl-red {{ color: {_RED}; }}
.nb-line {{
  margin: 5px 0;
  padding: 2px 0;
  line-height: 2.2;
  word-spacing: 0.08em;
  font-variant-numeric: tabular-nums;
}}
.nb-line.nb-gap {{
  margin: 14px 0;
  min-height: 8px;
  line-height: 0.4;
}}
.nb-line.nb-eq {{
  color: {_CHARCOAL};
  font-weight: 300;
}}
.nb-line.nb-eq-oneline {{
  white-space: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  max-width: 100%;
  scrollbar-width: thin;
}}
.nb-line.nb-eq-oneline::-webkit-scrollbar {{
  height: 4px;
}}
.nb-calc-block {{
  flex: 0 0 auto;
  max-width: 100%;
  min-width: 0;
  overflow-x: auto;
  overflow-y: visible;
}}
.nb-line.nb-eq-start {{
  margin-top: 20px;
  font-weight: 400;
  color: {_INK};
}}
.nb-line.nb-eq-start:first-child {{
  margin-top: 6px;
}}
.nb-sub {{
  margin: 8px 0 6px;
  font-weight: 700;
  font-size: 10pt;
  color: {_CHARCOAL};
  line-height: 2;
}}
.nb-line.nb-delta {{
  color: {_BRIGHT_GREEN};
  font-weight: 350;
  font-size: 10.5pt;
}}
.nb-line.nb-shear {{
  color: {_BLUE};
  font-weight: 350;
}}
.nb-line.nb-moment {{
  color: {_RED};
  font-weight: 350;
}}
.nb-line.nb-note {{
  color: {_ORANGE_NOTE};
  font-size: 9pt;
  font-weight: 300;
  line-height: 2.05;
  margin-top: 10px;
  padding-right: 4px;
  opacity: 0.95;
}}
.nb-sym {{
  font-family: 'Rubik', 'Times New Roman', serif;
  font-weight: 400;
  font-size: 1.05em;
  line-height: 1;
  vertical-align: -0.06em;
}}
.nb-sym-svg {{
  display: inline-block;
  vertical-align: -0.15em;
  margin-inline: 1px;
}}
.nb-black {{ color: {_INK}; }}
.nb-sub.nb-black {{ color: {_CHARCOAL}; }}
.nb-box {{
  display: inline-block;
  border: 1px solid rgba(30, 58, 95, 0.35);
  padding: 4px 12px;
  margin: 6px 0 10px;
  font-weight: 700;
  line-height: 1.65;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.35);
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
}}
.nb-box.nb-box-answer {{
  background: rgba(226, 240, 217, 0.42);
  border: 1px solid rgba(143, 173, 122, 0.75);
  color: {_CHARCOAL};
}}
.nb-eq-tail {{
  white-space: nowrap;
  display: inline;
}}
.nb-line.nb-eq .nb-box.nb-box-answer {{
  margin: 0 2px;
  vertical-align: baseline;
}}
.nb-forces-zone {{
  flex: 0 0 auto;
  margin-top: 14px;
  margin-bottom: 6px;
  width: 100%;
  overflow: hidden;
}}
.nb-forces-zone img {{
  width: calc(100% + 22px);
  height: auto;
  display: block;
  background: transparent;
  object-fit: contain;
  object-position: left top;
  margin-left: -22px;
  transform: scale(0.8) translateX(99px);
  transform-origin: left top;
}}
.nb-point-calc-scroll {{
  flex: 1 1 auto;
  min-height: 0;
  margin-top: 10px;
  overflow-x: hidden;
  overflow-y: auto;
  padding-right: 2px;
  scrollbar-width: thin;
}}
.nb-point-calc-scroll .nb-point-grid {{
  margin-top: 0;
  align-items: start;
}}
.nb-point-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
  width: 100%;
}}
.nb-point-col {{
  border: 1px dashed rgba(15, 23, 42, 0.22);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.18);
  padding: 8px 10px;
  min-width: 0;
}}
.nb-point-col h4 {{
  margin: 0 0 6px 0;
  font-size: 10pt;
  font-weight: 700;
  color: {_INK};
  direction: ltr;
  text-align: left;
}}
.nb-point-col .nb-line {{
  margin: 3px 0;
  padding: 0;
  line-height: 1.85;
  font-size: 9.5pt;
  direction: ltr;
  text-align: left;
}}
.nb-xzero-card {{
  margin-top: 24px;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px dashed rgba(217, 48, 37, 0.45);
  background: rgba(255, 255, 255, 0.28);
  text-align: right;
}}
.nb-xzero-card .nb-line {{
  color: {_RED};
  font-weight: 700;
  font-size: 11pt;
  line-height: 2.35;
}}
.nb-xzero-title {{
  margin: 0 0 8px 0;
  font-size: 10pt;
  font-weight: 700;
  color: {_RED};
  opacity: 0.9;
}}
.nb-col-calc .nb-line,
.nb-col-calc .nb-sub,
.nb-col-calc .nb-box {{
  font-family: inherit;
}}
.nb-line sub,
.nb-line sup {{
  font-size: 0.82em;
  line-height: 0;
  font-weight: 600;
}}
"""

# PyMuPDF — בלי calc(vw), transform, @import או base64 ב־@font-face
_NOTEBOOK_PDF_OVERRIDES = f"""
html, body {{ background: #ffffff; margin: 0; padding: 0; direction: ltr; }}
.nb-outer {{ background: #ffffff; padding: 0; display: block; }}
.nb-page {{
  box-shadow: none;
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  height: auto;
  min-height: 297mm;
  overflow: visible;
  padding: 7mm 6mm 8mm;
  background-color: {_PAPER};
  background-image:
    linear-gradient({_GRID} 1px, transparent 1px),
    linear-gradient(90deg, {_GRID} 1px, transparent 1px);
  background-size: 11px 11px;
  border: 1px solid rgba(90, 70, 40, 0.4);
}}
.nb-row {{ height: auto; max-height: none; width: 100%; }}
.nb-col-left {{ width: 100%; flex: 1 1 100%; overflow: visible; min-width: 0; }}
.nb-beam-zone, .nb-forces-zone {{ overflow: visible; width: 100%; max-width: 100%; }}
.nb-beam-zone img, .nb-forces-zone img {{
  width: 100%;
  max-width: 100%;
  height: auto;
  margin-left: 0;
  transform: none;
  object-fit: contain;
  object-position: left top;
  background: transparent;
}}
.nb-calc-block, .nb-calc-block > div {{
  min-width: 0 !important;
  max-width: 100%;
  overflow: visible;
}}
.nb-line.nb-eq-oneline {{
  white-space: normal;
  overflow: visible;
  word-break: break-word;
}}
.nb-point-calc-scroll {{ overflow: visible; width: 100%; max-width: 100%; }}
.nb-point-grid {{
  width: 100%;
  max-width: 100%;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr);
}}
.nb-point-col {{
  min-width: 0;
  overflow-wrap: anywhere;
}}
.nb-point-col .nb-line {{
  white-space: normal;
  word-break: break-word;
  font-size: 8.5pt;
  line-height: 1.55;
}}
"""


def _pdf_font_face_css() -> str:
    """גופן Heebo מקובץ מקומי — תואם ל־fitz.Archive (לא base64)."""
    if not _HEEBO_TTF.is_file() or _HEEBO_TTF.stat().st_size < 8000:
        return ""
    return (
        "@font-face{font-family:Heebo;src:url(Heebo-Regular.ttf);"
        "font-weight:400;font-style:normal;}"
    )


def _notebook_css_for_pdf() -> str:
    css = _NOTEBOOK_IFRAME_CSS
    css = re.sub(r"@import\s+url\([^)]+\);\s*", "", css)
    css = re.sub(r"max-width:\s*calc\([^)]+\);", "max-width: 210mm;", css)
    css = re.sub(r"height:\s*calc\([^)]+\);", "height: auto;", css)
    css = re.sub(r"max-height:\s*calc\([^)]+\);", "max-height: none;", css)
    css = re.sub(r"width:\s*calc\([^)]+\);", "width: 100%;", css)
    css = re.sub(r"-webkit-[^:]+:[^;]+;", "", css)
    css = re.sub(r"scrollbar-width:\s*[^;]+;", "", css)
    css = re.sub(r"transform:\s*[^;]+;", "transform: none;", css)
    css = re.sub(r"margin-left:\s*-22px;", "margin-left: 0;", css)
    css = re.sub(r"[^{}]*::[^{]*\{[^}]*\}", "", css)
    return _pdf_font_face_css() + css + _NOTEBOOK_PDF_OVERRIDES


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


def _wrap_iframe_document(body: str) -> str:
    _ensure_notebook_font()
    css = _embedded_ui_font_face_css() + _NOTEBOOK_IFRAME_CSS
    return f"""<!DOCTYPE html>
<html lang="he">
<head><meta charset="utf-8"><style>{css}</style></head>
<body><div class="nb-outer"><article class="nb-page">{body}</article></div></body>
</html>"""


def _wrap_pdf_document(body: str) -> str:
    """HTML לייצוא PDF — CSS תואם PyMuPDF, ללא חיתוך iframe."""
    _ensure_notebook_font()
    css = _notebook_css_for_pdf()
    return f"""<!DOCTYPE html>
<html lang="he" dir="ltr">
<head><meta charset="utf-8"><style>{css}</style></head>
<body><div class="nb-outer"><article class="nb-page">{body}</article></div></body>
</html>"""


def _html_to_pdf_bytes(html: str) -> bytes:
    """דף מחברת מלא → PDF (רב־עמודי אם צריך)."""
    import fitz

    _ensure_notebook_font()
    archive = fitz.Archive(str(_FONT_DIR)) if _HEEBO_TTF.is_file() else None
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    mediabox = fitz.Rect(0, 0, 595.28, 841.89)
    where = mediabox
    story = fitz.Story(html=html, archive=archive)
    while True:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
        if not more:
            break
    writer.close()
    return buf.getvalue()


def _pdf_to_png_bytes(pdf_bytes: bytes, *, dpi: int = _EXPORT_DPI) -> bytes:
    """רינדור PDF → PNG (כל העמודים מחוברים אנכית) — זהה לתצוגת המחברת."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if doc.page_count == 0:
        doc.close()
        return b""
    if doc.page_count == 1:
        png = doc[0].get_pixmap(dpi=dpi, alpha=False).tobytes("png")
        doc.close()
        return png
    try:
        from PIL import Image
    except ImportError:
        png = doc[0].get_pixmap(dpi=dpi, alpha=False).tobytes("png")
        doc.close()
        return png
    pages: List[Any] = []
    for i in range(doc.page_count):
        pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
        pages.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    doc.close()
    width = pages[0].width
    height = sum(p.height for p in pages)
    canvas = Image.new("RGB", (width, height), _PAPER)
    y = 0
    for page in pages:
        canvas.paste(page, (0, y))
        y += page.height
    buf = io.BytesIO()
    canvas.save(buf, format="PNG", dpi=(dpi, dpi))
    return buf.getvalue()


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
    """בלוק 3 עמודות: Nx/Qx/Mx בנקודות — עם פירוק "מה שעובר" בנקודה."""

    def _fmt(v: float) -> str:
        return str(solver.format_number(float(v)))

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

    _re_labeled_num = re.compile(r"(?:Ax|Ay|By|Fx|Fy|Ma|R|M)\(([^)]*)\)")

    def _expr_numbers_only(expr: str) -> str:
        """נקודה ראשונה בכל עמודה — רק מספרים, בלי Ay/Ax וכו'."""
        return _re_labeled_num.sub(r"\1", expr)

    def _val_with_unit(val: float) -> str:
        s = _fmt(val)
        if abs(val) < 1e-9:
            return s
        return f"{s}t"

    n_lines = ['<div class="nb-point-col"><h4>N(x)</h4>']
    q_lines = ['<div class="nb-point-col"><h4>Q(x)</h4>']
    m_lines = ['<div class="nb-point-col"><h4>M(x)</h4>']
    prev_n: float | None = None
    prev_q: float | None = None
    prev_m: float | None = None
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

        def _diagram_step(prev: float | None, cur: float) -> str:
            """קפיצה בדיאגרמה: ערך לפני הנקודה ± גודל השינוי (כמו בגרף)."""
            if prev is None:
                return _fmt(cur)
            d = cur - prev
            if abs(d) < 1e-9:
                return _fmt(cur)
            if d > 0:
                return f"{_fmt(prev)}+{_fmt(abs(d))}"
            return f"{_fmt(prev)}-{_fmt(abs(d))}"

        def _point_row(sym: str, expr: str, prev: float | None, val: float) -> str:
            val_esc = html_lib.escape(_val_with_unit(val))
            if prev is None:
                expr_esc = html_lib.escape(_clean_math_text(_expr_numbers_only(expr)))
                return f"{sym}<sub>{lab_esc}</sub> = {expr_esc} = {val_esc}"
            step_esc = html_lib.escape(_clean_math_text(_diagram_step(prev, val)))
            return f"{sym}<sub>{lab_esc}</sub> = {step_esc} = {val_esc}"

        if prev_n is None or abs(n_val - prev_n) > 1e-9:
            n_lines.append(_nb_step_html(_point_row("N", n_expr, prev_n, n_val), "nb-line"))
            prev_n = n_val
        if prev_q is None or abs(q_val - prev_q) > 1e-9:
            q_lines.append(_nb_step_html(_point_row("Q", q_expr, prev_q, q_val), "nb-line"))
            prev_q = q_val
        if prev_m is None or abs(m_val - prev_m) > 1e-9:
            m_lines.append(_nb_step_html(_point_row("M", m_expr, prev_m, m_val), "nb-line"))
            prev_m = m_val
    n_lines.append("</div>")
    q_lines.append("</div>")
    m_lines.append("</div>")
    return '<div class="nb-point-grid">' + "".join(n_lines + q_lines + m_lines) + "</div>"


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
    y_n = y_bottom - 2.0 * beam_to_dim
    y_q = y_n - axis_gap
    y_m = y_q - axis_gap
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
    """משולש סגור (קודקוד על הקורה y=0). מחזיר y של הבסיס."""
    y_base = -tri_h
    ax.add_patch(
        Polygon(
            [(x - tri_w, y_base), (x, 0.0), (x + tri_w, y_base)],
            closed=True,
            fill=False,
            edgecolor=_INK,
            linewidth=_SUPPORT_LW,
            joinstyle="round",
            zorder=4,
        )
    )
    return y_base


def _draw_pin_support(
    ax: Any,
    x: float,
    tri_h: float = _SUPPORT_TRI_H,
    tri_w: float = _SUPPORT_TRI_W,
) -> None:
    """סמך שמאל (ציר): 5 קווי קרקע — לאורך הבסיס, נוטים שמאלה."""
    y_base = _draw_support_triangle(ax, x, tri_h, tri_w)
    y_ground = y_base - _PIN_HATCH_LEN
    for xa in (
        x + tri_w,
        x + tri_w * 0.5,
        x,
        x - tri_w * 0.5,
        x - tri_w,
    ):
        (ln,) = ax.plot(
            [xa - _PIN_HATCH_LEAN, xa],
            [y_ground, y_base],
            color=_INK,
            linewidth=_PIN_HATCH_LW,
            solid_capstyle="round",
            zorder=5,
        )
        ln.set_clip_on(False)


def _draw_roller_support(
    ax: Any,
    x: float,
    tri_h: float = _SUPPORT_TRI_H,
    tri_w: float = _SUPPORT_TRI_W,
) -> None:
    """סמך ימין (גלגל): שני עיגולים מתחת לפינות המשולש."""
    y_base = _draw_support_triangle(ax, x, tri_h, tri_w)
    r = _ROLLER_CIRCLE_R
    for xa in (x - tri_w, x + tri_w):
        circ = plt.Circle(
            (xa, y_base - r),
            r,
            fill=False,
            edgecolor=_INK,
            linewidth=_ROLLER_CIRCLE_LW,
            zorder=6,
        )
        circ.set_clip_on(False)
        ax.add_patch(circ)


def _draw_udl_line(
    ax: Any, x1: float, x2: float, stem: float, q_label: str | None = None
) -> None:
    """מפולג כמו לוח הקורה: קו עליון, חצים שראשם בקורה או בקו העומס."""
    # הורדת גובה הקו העליון (ופועל יוצא: קיצור הקווים הצדדיים)
    y_top = stem * (48.0 / 48.0)
    arr_mid = stem * (12.0 / 48.0)
    ax.plot([x1, x2], [y_top, y_top], color=_RED, linewidth=_NOTEBOOK_LOAD_LW_UDL_LINE, zorder=5)

    def _udl_arrow(x: float, y0: float, y1: float, lw: float) -> None:
        # חשוב: shrinkA/B=0 כדי שהחץ "יתחבר" לקו העליון ולקורה בלי רווחים.
        ax.annotate(
            "",
            xy=(x, y1),
            xytext=(x, y0),
            arrowprops=dict(
                arrowstyle="-|>",
                color=_RED,
                lw=lw,
                mutation_scale=10,
                shrinkA=0,
                shrinkB=0,
            ),
            zorder=6,
        )

    _udl_arrow(x1, y_top, 0.0, _NOTEBOOK_LOAD_LW_UDL_ARR)
    _udl_arrow(x2, y_top, 0.0, _NOTEBOOK_LOAD_LW_UDL_ARR)
    span = x2 - x1
    if span > 1e-9:
        for frac in (0.25, 0.5, 0.75):
            xc = x1 + frac * span
            # חצים פנימיים צריכים לרדת מהקו העליון למטה (לא לעלות).
            _udl_arrow(xc, y_top, y_top - arr_mid, _NOTEBOOK_LOAD_LW_UDL_MID)
    if q_label:
        ax.text(
            (x1 + x2) / 2,
            y_top + 0.1,
            q_label,
            ha="center",
            va="bottom",
            fontsize=_FS_BODY,
            color=_RED,
            fontweight="normal",
            zorder=6,
        )


def _moment_arc_thetas(m: float) -> Tuple[float, float]:
    """זוויות קשת מומנט — אורך ×1.35, רדיוס קבוע; חיובי/שלילי בחצאי מעגל נפרדים."""
    half = _NOTEBOOK_MOMENT_ARC_SPAN_DEG / 2.0
    # חיובי: אותה קשת כמו למטה, מוחזרת למעלה; שלילי בחצי המעגל הנגדי.
    if m >= 0:
        mid = _NOTEBOOK_MOMENT_ARC_MID_DEG
    else:
        mid = _NOTEBOOK_MOMENT_ARC_MID_DEG + 180.0
    t1 = mid - half
    t2 = mid + half
    if t2 >= 360.0:
        t2 -= 360.0
    if t1 < 0.0:
        t1 += 360.0
    return t1, t2


def _draw_moment_arc(
    ax: Any,
    x: float,
    m: float,
    scale: float = _NOTEBOOK_MOMENT_RAD,
    *,
    show_value: bool = True,
) -> None:
    """קשת ממורכזת בנקודה על הקורה; ראש חץ בסוף הקשת."""
    rad = scale
    t1, t2 = _moment_arc_thetas(m)
    ax.add_patch(
        Arc(
            (x, 0.0),
            rad * 2,
            rad * 2,
            angle=0,
            theta1=t1,
            theta2=t2,
            color=_RED,
            lw=_NOTEBOOK_LOAD_LW_MOMENT_ARC,
            zorder=5,
        )
    )
    # במומנט חיובי: מעבירים את ראש החץ לקצה השני של הקשת.
    t_head = t1 if m >= 0 else t2
    t_head_rad = np.deg2rad(t_head)
    xe = x + rad * np.cos(t_head_rad)
    ye = rad * np.sin(t_head_rad)
    tx = -rad * np.sin(t_head_rad)
    ty = rad * np.cos(t_head_rad)
    if m >= 0:
        tx = -tx
        ty = -ty
    tlen = float(np.hypot(tx, ty)) or 1.0
    ah = 0.055
    ax.annotate(
        "",
        xy=(xe, ye),
        xytext=(xe - tx / tlen * ah * 2.2, ye - ty / tlen * ah * 2.2),
        arrowprops=dict(
            arrowstyle="-|>", color=_RED, lw=_NOTEBOOK_LOAD_LW_MOMENT_HEAD, mutation_scale=9
        ),
        zorder=6,
    )
    if show_value:
        label_y = rad + 0.14 if m >= 0 else -(rad + 0.14)
        ax.text(
            x + 0.06 * (1 if m >= 0 else -1),
            label_y,
            f"{solver.format_number(abs(m))}",
            fontsize=_FS_BODY,
            color=_RED,
            fontweight="normal",
            ha="left" if m >= 0 else "right",
            va="bottom" if m >= 0 else "top",
            zorder=6,
        )


def _draw_loads_like_canvas(ax: Any, loads: List[dict], load_scale: float, *, show_values: bool = False) -> None:
    """עומסים כמו בלוח הקורה הראשי — כל חץ מצביע אל נקודת ההצבה על הקורה (y=0)."""
    # חשוב: לא לתת לגובה החצים "להתפוצץ" כשיש שילוב עומסים גדול (למשל נקודתי+מפוזר),
    # אחרת החצים נמתחים למעלה מחוץ לאזור השרטוט במחברת.
    stem = min(load_scale * _NOTEBOOK_LOAD_LEN_MULT, 0.62)
    for ld in loads:
        if ld["type"] == "point":
            x = float(ld["x"])
            fy = float(ld["Fy"])
            fx = float(ld.get("Fx", 0.0))
            fy_mag = abs(fy)
            if fy_mag > 1e-6 and abs(fx) < 1e-6:
                if fy < 0:
                    # Fy<0 = עומס כלפי מטה (מהקנבס) → חץ מלמעלה אל הקורה.
                    _draw_arrow(ax, x, stem, 0.0, _RED, lw=_NOTEBOOK_LOAD_LW_POINT)
                    if show_values:
                        ax.text(
                            x + 0.04,
                            stem + 0.06,
                            f"{solver.format_number(fy_mag)}",
                            fontsize=_FS_BODY,
                            color=_RED,
                        )
                else:
                    # Fy>0 = עומס כלפי מעלה → חץ מלמטה אל הקורה.
                    _draw_arrow(ax, x, -stem, 0.0, _RED, lw=_NOTEBOOK_LOAD_LW_POINT)
                    if show_values:
                        ax.text(
                            x + 0.04,
                            -stem - 0.06,
                            f"{solver.format_number(fy_mag)}",
                            fontsize=_FS_BODY,
                            color=_RED,
                        )
            elif fy_mag < 1e-6 and abs(fx) >= 1e-6:
                if fx > 0:
                    _draw_arrow_h(ax, x - stem, x, 0.0, _RED, lw=_NOTEBOOK_LOAD_LW_AXIAL)
                else:
                    _draw_arrow_h(ax, x + stem, x, 0.0, _RED, lw=_NOTEBOOK_LOAD_LW_AXIAL)
                if show_values:
                    ax.text(
                        x + (stem / 2 if fx < 0 else -stem / 2),
                        0.08,
                        f"{solver.format_number(abs(fx))}",
                        fontsize=_FS_BODY,
                        color=_RED,
                        ha="center",
                    )
            elif fy_mag > 1e-6:
                mag = float(np.hypot(fx, fy)) or 1.0
                tail_x = x - fx / mag * stem
                tail_y = -fy / mag * stem
                ax.annotate(
                    "",
                    xy=(x, 0.0),
                    xytext=(tail_x, tail_y),
                    arrowprops=dict(
                        arrowstyle="-|>", color=_RED, lw=_NOTEBOOK_LOAD_LW_INCL, mutation_scale=10
                    ),
                    zorder=5,
                )
                if show_values:
                    ax.text(
                        (x + tail_x) / 2,
                        tail_y + (0.08 if fy < 0 else -0.08),
                        f"{solver.format_number(mag)}",
                        fontsize=_FS_BODY,
                        color=_RED,
                        ha="center",
                    )
            else:
                _draw_arrow(ax, x, stem, 0.0, _RED, lw=_NOTEBOOK_LOAD_LW_POINT)
        elif ld["type"] == "distributed":
            q_lbl = f"{solver.format_number(abs(float(ld['w'])))}" if show_values else None
            _draw_udl_line(ax, float(ld["x1"]), float(ld["x2"]), stem, q_lbl)
        elif ld["type"] == "moment":
            _draw_moment_arc(ax, float(ld["x"]), float(ld["M"]), show_value=show_values)
        elif ld["type"] == "inclined":
            x = float(ld["x"])
            fx = float(ld["Fx"])
            fy = float(ld["Fy"])
            mag = float(np.hypot(fx, fy))
            if mag > 1e-9:
                tail_x = x - fx / mag * stem
                tail_y = -fy / mag * stem
                ax.annotate(
                    "",
                    xy=(x, 0.0),
                    xytext=(tail_x, tail_y),
                    arrowprops=dict(
                        arrowstyle="-|>", color=_RED, lw=_NOTEBOOK_LOAD_LW_INCL, mutation_scale=10
                    ),
                    zorder=5,
                )
                if show_values:
                    ax.text(
                        (x + tail_x) / 2,
                        tail_y - 0.08,
                        f"{solver.format_number(mag)}",
                        fontsize=_FS_BODY,
                        color=_RED,
                        ha="center",
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
    """שרטוט קורה + עומסים. show_values=False: רק אותיות נקודות על קו מידות (A,B,C…)."""
    Lf = float(L)
    ax.plot([0, Lf], [0, 0], color=_INK, linewidth=_BEAM_MAIN_LW, zorder=2, solid_capstyle="round")

    if abs(ra_pos - rb_pos) < 1e-9:
        _draw_pin_support(ax, ra_pos)
    else:
        if ra_pos <= rb_pos:
            _draw_pin_support(ax, ra_pos)
            _draw_roller_support(ax, rb_pos)
        else:
            _draw_pin_support(ax, rb_pos)
            _draw_roller_support(ax, ra_pos)

    load_scale = max(0.28, 0.05 * max(abs(ra_y), abs(rb_y), 8.0))
    _draw_loads_like_canvas(ax, loads, load_scale, show_values=show_values)

    if show_values:
        if abs(ra_y) > 1e-9:
            ax.text(
                ra_pos + 0.05,
                0.28,
                f"{solver.format_number(ra_y)} = Ay",
                fontsize=_FS_SMALL,
                color=_INK,
                fontweight="normal",
            )
        if abs(rb_y) > 1e-9:
            ax.text(
                rb_pos - 0.05,
                0.28,
                f"By = {solver.format_number(rb_y)}",
                fontsize=_FS_SMALL,
                color=_INK,
                fontweight="normal",
                ha="right",
            )
        if abs(ra_x) > 1e-9:
            magx = 0.22
            if ra_x > 0:
                ax.annotate(
                    "",
                    xy=(ra_pos + magx, 0.04),
                    xytext=(ra_pos, 0.04),
                    arrowprops=dict(arrowstyle="-|>", color=_INK, lw=1.1),
                )
                ax.text(
                    ra_pos + magx + 0.02,
                    0.1,
                    f"{solver.format_number(ra_x)} = Ax",
                    fontsize=_FS_SMALL,
                    color=_INK,
                )
            else:
                ax.annotate(
                    "",
                    xy=(ra_pos - magx, 0.04),
                    xytext=(ra_pos, 0.04),
                    arrowprops=dict(arrowstyle="-|>", color=_INK, lw=1.1),
                )
                ax.text(
                    ra_pos - magx - 0.2,
                    0.1,
                    f"{solver.format_number(ra_x)} = Ax",
                    fontsize=_FS_SMALL,
                    color=_INK,
                )

    stations = station_labels(loads, L, ra_pos, rb_pos)
    layout = _notebook_layout()
    dim_bottom = _draw_notebook_dimension_lines(
        ax, stations, layout, support_pair=(ra_pos, rb_pos)
    )

    pad_x = max(0.15, 0.04 * Lf)
    ax.set_xlim(-pad_x, Lf + pad_x)
    if set_limits:
        ax.set_ylim(min(layout["y_bottom"], dim_bottom), layout["y_top"])
    ax.axis("off")


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


def _beam_diagram_ylim(values: np.ndarray, *, floor: float = 0.5) -> Tuple[float, float]:
    """טווח אנכי סביב הקורה (y=0) — לא ציר קרטזי."""
    yr = float(max(np.max(np.abs(np.asarray(values, dtype=float))), floor))
    pad = 0.34 * yr
    return -yr - pad, yr + pad


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
    xs = np.asarray(xs, dtype=float)
    normals = np.asarray(normals, dtype=float)
    if len(xs) and xs[0] > 1e-9:
        xs = np.concatenate(([0.0], xs))
        normals = np.concatenate(([float(normals[0])], normals))

    _configure_beam_diagram_ax(ax, Lf, x_pad, normals, transparent=transparent, paper=False)
    _plot_zero_baseline_cartesian(ax, Lf)
    # להתחיל מהקורה (y=0) גם אם יש קפיצה בתחילת הגרף
    if len(xs):
        ax.plot([0.0, 0.0], [0.0, float(normals[0])], color=_GREEN, linewidth=_DIAG_LW, zorder=3)
    ax.step(xs, normals, where="post", color=_GREEN, linewidth=_DIAG_LW, zorder=3)
    ax.invert_yaxis()
    ymin, ymax = ax.get_ylim()
    _draw_beam_reference(ax, Lf, crit, ymin, ymax)


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
    xs = np.asarray(xs, dtype=float)
    shears = np.asarray(shears, dtype=float)
    if len(xs) and xs[0] > 1e-9:
        xs = np.concatenate(([0.0], xs))
        shears = np.concatenate(([float(shears[0])], shears))

    _configure_beam_diagram_ax(ax, Lf, x_pad, shears, transparent=transparent, paper=False)
    _plot_zero_baseline_cartesian(ax, Lf)
    if len(xs):
        ax.plot([0.0, 0.0], [0.0, float(shears[0])], color=_BLUE, linewidth=_DIAG_LW, zorder=3)
    ax.step(xs, shears, where="post", color=_BLUE, linewidth=_DIAG_LW, zorder=3)
    ymin, ymax = ax.get_ylim()
    _draw_beam_reference(ax, Lf, crit, ymin, ymax)


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
    xs = np.asarray(xs, dtype=float)
    moments = np.asarray(moments, dtype=float)
    if len(xs) and xs[0] > 1e-9:
        xs = np.concatenate(([0.0], xs))
        moments = np.concatenate(([float(moments[0])], moments))

    _configure_beam_diagram_ax(ax, Lf, x_pad, moments, transparent=transparent, paper=False)
    _plot_zero_baseline_cartesian(ax, Lf)
    if len(xs):
        ax.plot([0.0, 0.0], [0.0, float(moments[0])], color=_RED, linewidth=_DIAG_LW, zorder=3)
    ax.plot(xs, moments, color=_RED, linewidth=_DIAG_LW, zorder=3, solid_capstyle="round")
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
    fig, ax = plt.subplots(1, 1, figsize=(7.8, fig_h), facecolor="none")
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
    fig.subplots_adjust(left=0.09, right=0.99, top=0.98, bottom=0.06)
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
) -> Any:
    """קורה + מידות בלבד (ללא דיאגרמות N/Q/M) — לתצוגה זמנית במחברת."""
    _notebook_mpl_rc()
    fig, ax = plt.subplots(1, 1, figsize=(7.8, 2.15), facecolor="none")
    _prep_figure_transparent(fig)
    _prep_axis_on_paper(ax, grid=False)
    _draw_beam_schematic(ax, L, loads, ra_pos, rb_pos, ra_x, ra_y, rb_y)
    # חשוב: לא לדרוס set_ylim / set_xlim של _draw_beam_schematic,
    # אחרת קו המידה בין הסמכים והמספר נחתכים.
    fig.subplots_adjust(left=0.09, right=0.99, top=0.98, bottom=0.06)
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
        fig_download = build_beam_figure(L, loads, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y)
        png_download = _fig_to_png_bytes(fig_download, style="export", pad_inches=0.06)
        plt.close(fig_download)

        fig_display = build_beam_schematic_figure(L, loads, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y)
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

        # download: full page (beam + diagrams)
        fig_download = plt.figure(figsize=(7.8, 7.2), facecolor="none")
        _prep_figure_transparent(fig_download)
        gs = fig_download.add_gridspec(
            4,
            1,
            height_ratios=[1.05, 1, 1, 1],
            hspace=0.16,
            left=0.12,
            right=0.98,
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
        fig_display = plt.figure(figsize=(7.8, 2.15), facecolor="none")
        _prep_figure_transparent(fig_display)
        ax_d = fig_display.add_subplot(1, 1, 1)
        _prep_axis_on_paper(ax_d, grid=False)
        _draw_cantilever_beam_schematic(
            ax_d, L, loads, ra_y=float(result.get("R_Ay", 0.0))
        )
        fig_display.subplots_adjust(left=0.09, right=0.99, top=0.98, bottom=0.06)

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
    # מרחק בין שורות חישוב: מעלים את השורה השנייה משבצת אחת (11px),
    # וכל שורה נוספת תשתמש באותו מרווח (כלומר אותו offset שלילִי).
    _LINE_UP_ONE_SQUARE = "margin-top:-11px;"
    if not has_fx:
        ax_eq_html = html_lib.escape(f"Ax = 0 {_U_FORCE}")
        ax_ans_html = (
            f'<span class="nb-box nb-box-answer">{html_lib.escape(f"Ax = 0 {_U_FORCE}")}</span>'
        )
        ax_line = f"{ax_eq_html}&nbsp;&nbsp;&nbsp;, {ax_ans_html}"
    else:
        parts: List[str] = ["Ax"]
        for _, fx in axial_terms:
            mag = solver.format_number(abs(fx))
            if fx >= 0:
                parts.append(f"+ {mag}")
            else:
                parts.append(f"− {mag}")
        ax_eq_html = html_lib.escape(_clean_math_text(_join_calc_terms(parts) + " = 0"))
        ax_ans_html = (
            f'<span class="nb-box nb-box-answer">'
            f'{html_lib.escape(f"Ax = {solver.format_number(ax_value)} {_U_FORCE}")}'
            f"</span>"
        )
        ax_line = f"{ax_eq_html}&nbsp;&nbsp;&nbsp;, {ax_ans_html}"

    def _calc_row_with_answer(eq_html: str, ans_name: str, ans_value: float, ans_unit: str, line_style: str) -> str:
        inner = f"{eq_html}{_nb_eq_answer_tail(ans_name, ans_value, ans_unit)}"
        return _nb_calc_eq_row(inner, line_style)

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
        """מחזיר מחרוזות של (כוח·מרחק) לכל עומס סביב נקודה, בסימן מתאים."""
        out: List[str] = []
        for ld in loads:
            t = ld.get("type")
            if t == "point":
                fy = float(ld.get("Fy", 0.0) or 0.0)
                dx = float(ld.get("x", 0.0) or 0.0) - float(x_ref)
                if abs(fy) < 1e-9 or abs(dx) < 1e-9:
                    continue
                m = -fy * dx
                body = f"({solver.format_number(abs(fy))}·{solver.format_number(abs(dx))})"
                out.append(f"+ {body}" if m >= 0 else f"− {body}")
            elif t == "inclined":
                fy = float(ld.get("Fy", 0.0) or 0.0)
                dx = float(ld.get("x", 0.0) or 0.0) - float(x_ref)
                if abs(fy) < 1e-9 or abs(dx) < 1e-9:
                    continue
                m = -fy * dx
                body = f"({solver.format_number(abs(fy))}·{solver.format_number(abs(dx))})"
                out.append(f"+ {body}" if m >= 0 else f"− {body}")
            elif t == "distributed":
                w = float(ld.get("w", 0.0) or 0.0)
                x1 = float(ld.get("x1", 0.0) or 0.0)
                x2 = float(ld.get("x2", 0.0) or 0.0)
                span = x2 - x1
                if abs(w) < 1e-9 or span <= 1e-9:
                    continue
                resultant = w * span
                centroid = (x1 + x2) / 2.0
                dx = centroid - float(x_ref)
                m = -resultant * dx
                body = (
                    f"({solver.format_number(abs(resultant))}·{solver.format_number(abs(dx))})"
                )
                out.append(f"+ {body}" if m >= 0 else f"− {body}")
            elif t == "moment":
                mm = float(ld.get("M", 0.0) or 0.0)
                if abs(mm) < 1e-9:
                    continue
                body = f"({solver.format_number(abs(mm))})"
                out.append(f"+ {body}" if mm >= 0 else f"− {body}")
        return out

    if support_mode == "supports" and abs(rb_pos - ra_pos) > 1e-9:
        arm_b = float(rb_pos - ra_pos)
        arm_a = float(ra_pos - rb_pos)
        m_terms_a = _m_term_strings_about(float(ra_pos))
        ma_line = f"{_sym_sigma()}Ma = 0"
        ma_parts = list(m_terms_a) if m_terms_a else ["0"]
        ma_parts.append(f"+ By·{solver.format_number(arm_b)}")
        ma_calc = _join_calc_terms(ma_parts)
        ma_res_name = "By"
        ma_res_value = float(rb_y)
        ma_res_unit = _U_FORCE
        mb_line = f"{_sym_sigma()}Mb = 0"
        m_terms_b = _m_term_strings_about(float(rb_pos))
        mb_parts = list(m_terms_b) if m_terms_b else ["0"]
        mb_parts.append(f"+ Ay·{solver.format_number(abs(arm_a))}")
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

    if ma_calc:
        ma_eq_html = html_lib.escape(_clean_math_text(ma_calc))
        ma_inner = f"{ma_eq_html}{_nb_eq_answer_tail(ma_res_name, ma_res_value, ma_res_unit)}"
        ma_calc_html = _nb_calc_eq_row(ma_inner, _LINE_UP_ONE_SQUARE)
    else:
        ma_calc_html = ""

    if support_mode == "supports" and mb_line:
        mb_eq_html = html_lib.escape(_clean_math_text(mb_calc))
        ay_calc_html = _calc_row_with_answer(mb_eq_html, ay_res_name, ay_res_value, ay_res_unit, _LINE_UP_ONE_SQUARE)
    elif support_mode == "cantilever" and ay_header_line:
        mg_eq_html = html_lib.escape(_clean_math_text(mg_calc))
        mg_inner = f"{mg_eq_html}{_nb_eq_answer_tail(ma_res_name, ma_res_value, ma_res_unit)}"
        mg_calc_html = _nb_calc_eq_row(mg_inner, _LINE_UP_ONE_SQUARE)
        ay_eq_html = html_lib.escape(_clean_math_text(ay_calc))
        ay_inner = f"{ay_eq_html}{_nb_eq_answer_tail(ay_res_name, ay_res_value, ay_res_unit)}"
        ay_calc_html = _nb_calc_eq_row(ay_inner, _LINE_UP_ONE_SQUARE)
        fy_calc_html = ""
        if fy_calc:
            fy_calc_html = _nb_calc_eq_row(
                f"{html_lib.escape(_clean_math_text(fy_calc))}{_nb_eq_zero_tail()}",
                _LINE_UP_ONE_SQUARE,
            )
    else:
        ay_calc_html = ""
        mg_calc_html = ""
        fy_calc_html = ""

    calc_rows: List[str] = [
        _nb_step_html_style(f"{_sym_sigma()}Fx = 0", "nb-eq"),
        _nb_calc_eq_row(ax_line, _LINE_UP_ONE_SQUARE),
    ]
    if support_mode == "cantilever" and cantilever_result is not None:
        calc_rows.append(_nb_step_html_style(mg_line, "nb-eq"))
        if mg_calc_html:
            calc_rows.append(mg_calc_html)
        calc_rows.append(_nb_step_html_style(ay_header_line, "nb-eq"))
        if ay_calc_html:
            calc_rows.append(ay_calc_html)
    else:
        if ma_line:
            calc_rows.append(_nb_step_html_style(ma_line, "nb-eq"))
        if ma_calc_html:
            calc_rows.append(ma_calc_html)
        if mb_line:
            calc_rows.append(_nb_step_html_style(mb_line, "nb-eq"))
        if ay_calc_html:
            calc_rows.append(ay_calc_html)

    return "\n".join(
        [
            '<div style="width:100%;display:flex;justify-content:flex-start;">',
            '<div class="nb-calc-block" style="width:100%;flex:0 0 auto;max-width:100%;margin-top:-34px;direction:ltr;text-align:left;unicode-bidi:plaintext;padding:0 6px 0 0;">',
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
) -> Any:
    """דיאגרמות N, Q, M — מתחת לקורה בשמאל."""
    positions = solver.critical_x_positions(loads, L, ra_pos, rb_pos)
    xs = solver.beam_plot_x_coords(L, positions)
    moments = np.array([solver.bending_moment(x, loads, ra_y, rb_y, ra_pos, rb_pos) for x in xs])
    shears = np.array([solver.shear_force(x, loads, ra_y, rb_y, ra_pos, rb_pos) for x in xs])
    normals = np.array([solver.normal_force(x, loads, ra_x, ra_pos) for x in xs])
    _notebook_mpl_rc()
    fig = plt.figure(figsize=(7.8, 3.7), facecolor="none")
    _prep_figure_transparent(fig)
    gs = fig.add_gridspec(
        3,
        1,
        height_ratios=[1.0, 1.0, 1.0],
        hspace=0.16,
        left=0.09,
        right=0.99,
        top=0.98,
        bottom=0.08,
    )
    ax_n = fig.add_subplot(gs[0])
    Lf = float(L)
    x_pad = 0.0
    crit = station_labels(loads, L, ra_pos, rb_pos)

    _plot_n_on_beam_clean(ax_n, xs, normals, Lf, x_pad, crit, transparent=False)
    _diagram_titles(fig, ax_n, "N(x)", _U_FORCE, _GREEN, Lf=Lf)

    ax_v = fig.add_subplot(gs[1], sharex=ax_n)
    _plot_q_on_beam_clean(ax_v, xs, shears, Lf, x_pad, crit, transparent=False)
    _diagram_titles(fig, ax_v, "Q(x)", _U_FORCE, _BLUE, Lf=Lf)

    ax_m = fig.add_subplot(gs[2], sharex=ax_n)
    _plot_m_on_beam_clean(ax_m, xs, moments, Lf, x_pad, crit, transparent=False)
    _diagram_titles(fig, ax_m, "M(x)", _U_MOMENT, _RED, Lf=Lf)

    return fig


def build_cantilever_forces_figure(loads: List[dict], L: float, result: Dict[str, Any]) -> Any:
    """דיאגרמות N, Q, M לזיז — מתחת למשוואות."""
    xs = np.asarray(result["xs"], dtype=float)
    normals = np.asarray(result["normal"], dtype=float)
    shears = np.asarray(result["shear"], dtype=float)
    moments = np.asarray(result["moment"], dtype=float)
    _notebook_mpl_rc()
    fig = plt.figure(figsize=(7.8, 3.7), facecolor="none")
    _prep_figure_transparent(fig)
    gs = fig.add_gridspec(
        3,
        1,
        height_ratios=[1.0, 1.0, 1.0],
        hspace=0.16,
        left=0.09,
        right=0.99,
        top=0.98,
        bottom=0.08,
    )
    ax_n = fig.add_subplot(gs[0])
    Lf = float(L)
    x_pad = 0.0
    crit = _cantilever_station_labels(loads, L)

    _plot_n_on_beam_clean(ax_n, xs, normals, Lf, x_pad, crit, transparent=False)
    _diagram_titles(fig, ax_n, "N(x)", _U_FORCE, _GREEN, Lf=Lf)

    ax_v = fig.add_subplot(gs[1], sharex=ax_n)
    _plot_q_on_beam_clean(ax_v, xs, shears, Lf, x_pad, crit, transparent=False)
    _diagram_titles(fig, ax_v, "Q(x)", _U_FORCE, _BLUE, Lf=Lf)

    ax_m = fig.add_subplot(gs[2], sharex=ax_n)
    _plot_m_on_beam_clean(ax_m, xs, moments, Lf, x_pad, crit, transparent=False)
    _diagram_titles(fig, ax_m, "M(x)", _U_MOMENT, _RED, Lf=Lf)

    return fig


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
    """תמונה משולבת להורדה (קורה + דיאגרמות)."""
    _notebook_mpl_rc()
    fig = plt.figure(figsize=(7.8, 6.5), facecolor=_PAPER)
    gs = fig.add_gridspec(
        4, 1, height_ratios=[0.95, 0.88, 0.88, 0.88], hspace=0.12, left=0.14, right=0.995, top=0.98, bottom=0.06
    )
    ax_beam = fig.add_subplot(gs[0])
    ax_beam.set_facecolor(_PAPER)
    _draw_beam_schematic(ax_beam, L, loads, ra_pos, rb_pos, ra_x, ra_y, rb_y)
    positions = solver.critical_x_positions(loads, L, ra_pos, rb_pos)
    xs = solver.beam_plot_x_coords(L, positions)
    moments = np.array([solver.bending_moment(x, loads, ra_y, rb_y, ra_pos, rb_pos) for x in xs])
    shears = np.array([solver.shear_force(x, loads, ra_y, rb_y, ra_pos, rb_pos) for x in xs])
    normals = np.array([solver.normal_force(x, loads, ra_x, ra_pos) for x in xs])
    Lf = float(L)
    x_pad = _beam_x_pad(Lf)
    crit = station_labels(loads, L, ra_pos, rb_pos)

    ax_n = fig.add_subplot(gs[1])
    _plot_n_on_beam(ax_n, xs, normals, Lf, x_pad, crit, transparent=False, paper=True)
    _diagram_titles(fig, ax_n, "N(x)", _U_FORCE, _GREEN, Lf=Lf)

    ax_v = fig.add_subplot(gs[2], sharex=ax_n)
    _plot_q_on_beam(ax_v, xs, shears, Lf, x_pad, crit, transparent=False, paper=True)
    _diagram_titles(fig, ax_v, "Q(x)", _U_FORCE, _BLUE, Lf=Lf)

    ax_m = fig.add_subplot(gs[3], sharex=ax_n)
    _plot_m_on_beam(ax_m, xs, moments, Lf, x_pad, crit, transparent=False, paper=True)
    _diagram_titles(fig, ax_m, "M(x)", _U_MOMENT, _RED, Lf=Lf)

    return fig


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


def _nb_calc_eq_row(inner_html: str, line_style: str = "") -> str:
    """שורת משוואה מלאה (כולל =0 ותשובה) — שורה אחת, גלילה אם ארוך."""
    return _nb_step_html_style(inner_html, "nb-eq nb-eq-oneline", line_style)


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
        body = f"{lhs}={solver.format_number(abs(v))}"
        raw.append(f"+ {body}" if v >= 0 else f"− {body}")
    if not raw:
        return solver.format_number(total)
    return _join_calc_terms(raw) + f" = {solver.format_number(total)}"


def _nb_eq_zero_tail() -> str:
    """'= 0' בסוף משוואה — לא נשבר לשורה נפרדת."""
    return '<span class="nb-eq-tail"> = 0</span>'


def _nb_eq_answer_tail(ans_name: str, ans_value: float, ans_unit: str) -> str:
    """'= 0' + פסיק + תשובה — נשארים באותה שורה אחרי המשוואה."""
    ans_txt = _clean_math_text(
        f"{ans_name} = {solver.format_number(ans_value)} {ans_unit}".strip()
    )
    ans_html = f'<span class="nb-box nb-box-answer">{html_lib.escape(ans_txt)}</span>'
    return f'<span class="nb-eq-tail"> = 0&nbsp;&nbsp;&nbsp;,&nbsp;{ans_html}</span>'


def _nb_answer_box(inner_html: str) -> str:
    return f'<p class="nb-line nb-eq"><span class="nb-box nb-box-answer">{inner_html}</span></p>'


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
    eq = _equilibrium_sections(loads, ra_pos, rb_pos, ra_x, ra_y, rb_y)
    rows = _values_at_stations(loads, L, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y)
    s = eq["sums"]
    parts: List[str] = [
        '<div class="nb-col-calc nb-flow">',
        '<div class="nb-block">',
        '<h2 class="nb-calc-title">מציאת ריאקציות — כוחות תגובה בסמכים</h2>',
    ]
    parts.append(_nb_step_html(f"{_sym_sigma()}F<sub>x</sub> = 0", "nb-eq nb-eq-start"))
    if eq["fx_lines"]:
        parts.append(
            _nb_step(
                _join_eq_value_lines_minus_only(eq["fx_lines"], float(s["sum_fx"])),
                "nb-eq",
            )
        )
    parts.append(
        _nb_step(
            f"Ax = −ΣFx = −({solver.format_number(s['sum_fx'])}) = "
            f"{solver.format_number(ra_x)} {_U_FORCE}",
            "nb-eq",
        )
    )
    if abs(ra_x) > 1e-9:
        parts.append(_nb_answer_box(f"Ax = {_esc_num(ra_x)} {_U_FORCE}"))
    parts.append(_nb_step(""))
    parts.append(_nb_step_html(f"{_sym_sigma()}M<sub>A</sub> = 0", "nb-eq nb-eq-start"))
    parts.append(_nb_step("סכום המומנטים סביב A:", "nb-sub nb-black"))
    if eq["ma_lines"]:
        parts.append(
            _nb_step(
                _join_eq_value_lines_minus_only(
                    eq["ma_lines"], float(s["moment_about_ra"])
                ),
                "nb-eq",
            )
        )
    parts.append(
        _nb_step(
            f"By = {solver.format_number(s['moment_about_ra'])}/{solver.format_number(eq['arm_b'])} "
            f"= {solver.format_number(rb_y)} {_U_FORCE}",
            "nb-eq",
        )
    )
    parts.append(_nb_answer_box(f"By = {_esc_num(rb_y)} {_U_FORCE}"))
    parts.append(_nb_step(""))
    parts.append(_nb_step_html(f"{_sym_sigma()}M<sub>B</sub> = 0", "nb-eq nb-eq-start"))
    parts.append(_nb_step("סכום המומנטים סביב B:", "nb-sub nb-black"))
    if eq["mb_lines"]:
        parts.append(
            _nb_step(
                _join_eq_value_lines_minus_only(
                    eq["mb_lines"], float(s["moment_about_rb"])
                ),
                "nb-eq",
            )
        )
    parts.append(
        _nb_step(
            f"Ay = −({solver.format_number(s['moment_about_rb'])}) / "
            f"({solver.format_number(eq['arm_a'])}) = {solver.format_number(ra_y)} {_U_FORCE}",
            "nb-eq",
        )
    )
    parts.append(_nb_answer_box(f"Ay = {_esc_num(ra_y)} {_U_FORCE}"))
    parts.append(
        _nb_step_html(
            f"{_sym_sigma()}F<sub>y</sub> + Ay + By = {solver.format_number(eq['fy_check'])}",
            "nb-eq",
        )
    )
    parts.append("</div>")

    parts.append('<div class="nb-block">')
    parts.append('<p class="nb-block-label nb-lbl-green">בדיקות חתך — כוח צירי (Δ)</p>')
    for r in rows:
        lab = r["label"]
        n_val = float(r["N"])
        n_l = float(r.get("N_left", n_val))
        n_r = float(r.get("N_right", n_val))
        if abs(n_l - n_r) > 1e-4:
            parts.append(
                _nb_step_html(
                    f"{_sym_delta()}<sub>{lab}</sub>: N<sub>L</sub> = {solver.format_number(n_l)}, "
                    f"N<sub>R</sub> = {solver.format_number(n_r)} {_U_FORCE}",
                    "nb-delta",
                )
            )
        else:
            parts.append(
                _nb_step_html(
                    f"{_sym_delta()}<sub>{lab}</sub> — N<sub>{lab}</sub> = "
                    f"{solver.format_number(n_val)} {_U_FORCE}",
                    "nb-delta",
                )
            )

    parts.append('<p class="nb-block-label nb-lbl-blue">גזירה Q</p>')
    for r in rows:
        parts.append(
            _nb_step_html(
                f"Q<sub>{r['label']}</sub> = {solver.format_number(r['Q'])} {_U_FORCE}",
                "nb-shear",
            )
        )

    parts.append('<p class="nb-block-label nb-lbl-red">מומנטים M</p>')
    for r in rows:
        parts.append(
            _nb_step_html(
                f"M<sub>{r['label']}</sub> = {solver.format_number(r['M'])} {_U_MOMENT}",
                "nb-moment",
            )
        )
    parts.append(_moment_handwriting_note())
    xzero = _shear_zero_card_html(loads, L, ra_pos, rb_pos, ra_y, rb_y)
    if xzero:
        parts.append(xzero)
    else:
        for zn in _shear_zero_notes(loads, L, ra_pos, rb_pos, ra_y, rb_y):
            parts.append(_nb_step(zn, "nb-shear"))
    parts.append("</div></div>")
    return "\n".join(parts)


def _fig_to_png_bytes(
    fig: Any,
    *,
    style: str = "embed",
    pad_inches: float = 0.02,
) -> bytes:
    """
    style='embed' — PNG שקוף להטמעה ב-HTML (רשת CSS של המחברת).
    style='export' — נייר מחברת + רשת, dpi גבוה (ייצוא עצמאי).
    """
    buf = io.BytesIO()
    if style == "export":
        _prep_figure_notebook_paper(fig)
        fig.savefig(
            buf,
            format="png",
            dpi=_EXPORT_DPI,
            transparent=False,
            facecolor=_PAPER,
            edgecolor=_PAPER,
            bbox_inches="tight",
            pad_inches=pad_inches,
        )
    else:
        fig.savefig(
            buf,
            format="png",
            dpi=_EMBED_DPI,
            transparent=True,
            facecolor="none",
            edgecolor="none",
            bbox_inches="tight",
            pad_inches=pad_inches,
        )
    buf.seek(0)
    return buf.getvalue()


def build_page_html(
    loads: List[dict],
    L: float,
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_x: float,
    rb_y: float,
) -> Tuple[str, bytes, bytes]:
    png_display, png_download = _notebook_graphics_assets(
        mode="supports",
        loads=loads,
        L=L,
        ra_pos=ra_pos,
        rb_pos=rb_pos,
        ra_x=ra_x,
        ra_y=ra_y,
        rb_x=rb_x,
        rb_y=rb_y,
    )
    fig_forces = build_forces_figure(L, loads, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y)
    png_forces = _fig_to_png_bytes(fig_forces, style="embed", pad_inches=0.03)
    plt.close(fig_forces)
    rows_pts = _values_at_stations(loads, L, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y)
    pts_html = _point_calc_grid_html(
        rows_pts,
        loads=loads,
        support_mode="supports",
        L=L,
        ra_pos=ra_pos,
        rb_pos=rb_pos,
        ra_x=ra_x,
        ra_y=ra_y,
        rb_y=rb_y,
    )

    forces_html = (
        f'<div class="nb-forces-zone">'
        f'<img src="data:image/png;base64,{base64.b64encode(png_forces).decode("ascii")}" alt="NQM diagrams"/>'
        f"</div>"
    )
    pts_scroll = f'<div class="nb-point-calc-scroll">{pts_html}</div>'
    body = _notebook_graphics_html(
        png_display,
        _notebook_calc_stub_under_beam(
            loads,
            ra_x,
            support_mode="supports",
            ra_pos=ra_pos,
            rb_pos=rb_pos,
            ra_y=ra_y,
            rb_y=rb_y,
        )
        + forces_html
        + pts_scroll,
    )
    pdf_bytes = _html_to_pdf_bytes(_wrap_pdf_document(body))
    png_page = _pdf_to_png_bytes(pdf_bytes, dpi=_EXPORT_DPI)
    return _wrap_iframe_document(body), png_page, pdf_bytes


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


def build_cantilever_page_html(loads: List[dict], L: float, result: Dict[str, Any]) -> Tuple[str, bytes, bytes]:
    png_display, png_download = _notebook_graphics_assets(
        mode="cantilever",
        loads=loads,
        L=L,
        result=result,
    )
    fig_forces = build_cantilever_forces_figure(loads, L, result)
    png_forces = _fig_to_png_bytes(fig_forces, style="embed", pad_inches=0.03)
    plt.close(fig_forces)
    rows_pts = _cantilever_values_at_stations(loads, L, result)
    pts_html = _point_calc_grid_html(
        rows_pts,
        loads=loads,
        support_mode="cantilever",
        L=L,
        cantilever_result=result,
    )

    forces_html = (
        f'<div class="nb-forces-zone">'
        f'<img src="data:image/png;base64,{base64.b64encode(png_forces).decode("ascii")}" alt="NQM diagrams"/>'
        f"</div>"
    )
    pts_scroll = f'<div class="nb-point-calc-scroll">{pts_html}</div>'
    body = _notebook_graphics_html(
        png_display,
        _notebook_calc_stub_under_beam(
            loads,
            float(result.get("R_Ax", 0.0)),
            L=L,
            support_mode="cantilever",
            cantilever_result=result,
        )
        + forces_html
        + pts_scroll,
    )
    pdf_bytes = _html_to_pdf_bytes(_wrap_pdf_document(body))
    png_page = _pdf_to_png_bytes(pdf_bytes, dpi=_EXPORT_DPI)
    return _wrap_iframe_document(body), png_page, pdf_bytes


def render_cantilever_notebook(loads: List[dict], L: float, result: Dict[str, Any]) -> None:
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
