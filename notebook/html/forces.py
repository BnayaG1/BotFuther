# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
from typing import Any, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np

from notebook.constants import _BLUE, _GREEN, _RED, _U_FORCE, _U_MOMENT
from notebook.export.png import _fig_to_png_bytes
from notebook_pdf_layout import DEFAULT_BOT_LAYOUT, NotebookPdfLayout, forces_gaps_mm, panel_height_in


def _forces_diagram_html(
    png_n: bytes,
    png_q: bytes,
    png_m: bytes,
    layout: NotebookPdfLayout,
) -> str:
    zone_top, q_gap, m_gap = forces_gaps_mm(layout)
    b64n = base64.b64encode(png_n).decode("ascii")
    b64q = base64.b64encode(png_q).decode("ascii")
    b64m = base64.b64encode(png_m).decode("ascii")
    q_mt = f"margin-top:{q_gap}mm;" if q_gap > 0 else ""
    m_mt = f"margin-top:{m_gap}mm;" if m_gap > 0 else ""
    zone_mt = f"margin-top:{zone_top}mm;" if zone_top > 0 else ""
    img_style = "display:block;width:100%;max-width:100%;height:auto;margin-left:0;margin-right:0;"
    return (
        f'<div class="nb-forces-zone" style="{zone_mt}">'
        f'<img class="nb-forces-n" style="{img_style}" '
        f'src="data:image/png;base64,{b64n}" alt="N diagram"/>'
        f'<img class="nb-forces-q" style="{img_style}{q_mt}" '
        f'src="data:image/png;base64,{b64q}" alt="Q diagram"/>'
        f'<img class="nb-forces-m" style="{img_style}{m_mt}" '
        f'src="data:image/png;base64,{b64m}" alt="M diagram"/>'
        f"</div>"
    )


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
    build_force_panel_figure: Any,
    plot_n_clean: Any,
    plot_q_clean: Any,
    plot_m_clean: Any,
    prep_figure_notebook_paper: Any,
) -> str:
    """שלוש תמונות נפרדות + מרווחי CSS — גודל קבוע, בלי כיווץ A4."""
    pdf_layout = layout or DEFAULT_BOT_LAYOUT
    panel_h = panel_height_in(pdf_layout)
    x_pad = max(0.04, 0.015 * float(Lf))
    figs: list[Any] = []
    try:
        fig_n = build_force_panel_figure(
            xs,
            normals,
            Lf,
            x_pad,
            crit,
            plot_n_clean,
            "N(x)",
            _U_FORCE,
            _GREEN,
            wide=wide,
            panel_h_in=panel_h,
        )
        fig_q = build_force_panel_figure(
            xs,
            shears,
            Lf,
            x_pad,
            crit,
            plot_q_clean,
            "Q(x)",
            _U_FORCE,
            _BLUE,
            wide=wide,
            panel_h_in=panel_h,
        )
        fig_m = build_force_panel_figure(
            xs,
            moments,
            Lf,
            x_pad,
            crit,
            plot_m_clean,
            "M(x)",
            _U_MOMENT,
            _RED,
            wide=wide,
            panel_h_in=panel_h,
        )
        figs.extend([fig_n, fig_q, fig_m])
        png_n = _fig_to_png_bytes(
            fig_n, prep_figure_notebook_paper=prep_figure_notebook_paper, style="embed", pad_inches=0.02, bbox="figure"
        )
        png_q = _fig_to_png_bytes(
            fig_q, prep_figure_notebook_paper=prep_figure_notebook_paper, style="embed", pad_inches=0.02, bbox="figure"
        )
        png_m = _fig_to_png_bytes(
            fig_m, prep_figure_notebook_paper=prep_figure_notebook_paper, style="embed", pad_inches=0.02, bbox="figure"
        )
        return _forces_diagram_html(png_n, png_q, png_m, pdf_layout)
    finally:
        for fig in figs:
            plt.close(fig)

