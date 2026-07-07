# -*- coding: utf-8 -*-
from __future__ import annotations

from notebook.constants import (
    _BLUE,
    _BRIGHT_GREEN,
    _CHARCOAL,
    _GRID,
    _GRID_CELL_MM,
    _HEADER,
    _HIGHLIGHT_ANSWER_BORDER,
    _INK,
    _ORANGE_NOTE,
    _PAPER,
    _RED,
    _REACTION_SIGMA_GAP_MM,
    _UI_FONT_CSS,
)


def _css_square_grid_paper() -> str:
    """רשת ריבועים — לתצוגת דפדפן/iframe בלבד (PyMuPDF Story מתעלם מ-background-image)."""
    g = _GRID_CELL_MM
    return f"""
  background-color: {_PAPER};
  background-image:
    linear-gradient(to right, {_GRID} 1px, transparent 1px),
    linear-gradient(to bottom, {_GRID} 1px, transparent 1px);
  background-size: {g}mm {g}mm;
  background-repeat: repeat;
  background-position: left top;
"""


# NOTE: נשמר בשם המקורי כדי להימנע משינויי התנהגות.
NOTEBOOK_IFRAME_CSS = f"""
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
{_css_square_grid_paper()}
  border: 1px solid rgba(90, 70, 40, 0.4);
  box-shadow: 0 10px 28px rgba(0,0,0,0.28);
  overflow: hidden;
  font-family: {_UI_FONT_CSS};
}}
.nb-page .nb-row,
.nb-page .nb-col-left,
.nb-page .nb-beam-zone,
.nb-page .nb-forces-zone,
.nb-page .nb-calc-block,
.nb-page .nb-calc-block > div,
.nb-page .nb-point-calc-scroll {{
  background: transparent;
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
  display: inline-block;
  max-width: 100%;
  padding: 1px 6px;
  margin: 0 1px;
  border-radius: 3px;
  font-weight: 600;
  line-height: 1.3;
  background: #edf5ef;
  border: 1px solid {_HIGHLIGHT_ANSWER_BORDER};
  color: {_CHARCOAL};
}}
.nb-eq-tail {{
  white-space: nowrap;
  display: inline;
}}
.nb-line.nb-eq .nb-box.nb-box-answer {{
  margin: 0;
  padding: 0 5px;
  vertical-align: baseline;
  font-size: 0.98em;
}}
.nb-line.nb-eq.nb-ans-only {{
  white-space: normal;
  margin-top: -6px;
  padding: 0;
  line-height: 1.25;
}}
.nb-rx-table {{
  border-collapse: collapse;
  border: none;
  width: auto;
  max-width: 100%;
  margin: 0;
}}
.nb-calc-block .nb-rx-table + .nb-rx-table {{
  margin-top: {_REACTION_SIGMA_GAP_MM}mm;
}}
.nb-rx-table td {{
  border: none;
  padding: 0;
  vertical-align: baseline;
  line-height: 2.0;
  text-align: left;
  white-space: nowrap;
}}
"""

