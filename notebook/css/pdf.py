# -*- coding: utf-8 -*-
from __future__ import annotations

from notebook.constants import (
    _BLUE,
    _BRIGHT_GREEN,
    _CHARCOAL,
    _GREEN,
    _INK,
    _PAPER,
    _POINT_CALC_TOP_GAP_MM,
    _REACTION_SIGMA_GAP_MM,
    _RED,
    _UI_FONT_CSS,
)
from notebook.pdf_layout import PAGE_BREAK_CSS


# PyMuPDF Story — CSS ייעודי (לא iframe!) כדי שלא יישאר max-height:297mm / overflow:hidden
NOTEBOOK_PDF_TYPOGRAPHY_CSS = f"""
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
.nb-calc-block {{ max-width: 100%; min-width: 0; overflow: visible; }}
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


NOTEBOOK_PDF_LAYOUT_FIX = f"""
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
NOTEBOOK_PDF_OVERRIDES = f"""
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
"""


NOTEBOOK_PDF_WIDE_OVERRIDES = ""


def notebook_css_for_pdf(*, wide: bool = False, font_face_css: str = "") -> str:
    css = font_face_css + NOTEBOOK_PDF_TYPOGRAPHY_CSS + NOTEBOOK_PDF_OVERRIDES + NOTEBOOK_PDF_LAYOUT_FIX
    if wide:
        css += NOTEBOOK_PDF_WIDE_OVERRIDES
    return css

