# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from notebook_pdf_layout import DEFAULT_BOT_LAYOUT, NotebookPdfLayout, assert_page2_fits


def build_cantilever_page_html(
    loads: List[dict],
    L: float,
    result: Dict[str, Any],
    *,
    wide_layout: bool = False,
    pdf_layout: Optional[NotebookPdfLayout] = None,
    notebook_graphics_assets_fn: Any,
    cantilever_station_labels_fn: Any,
    build_forces_diagram_html_fn: Any,
    cantilever_values_at_stations_fn: Any,
    point_calc_grid_html_fn: Any,
    notebook_calc_stub_under_beam_fn: Any,
    build_bot_notebook_extra_html_fn: Any,
    notebook_graphics_html_fn: Any,
    wrap_pdf_document_fn: Any,
    html_to_pdf_bytes_fn: Any,
    pdf_to_png_bytes_fn: Any,
    wrap_iframe_document_fn: Any,
    export_dpi: int,
) -> Tuple[str, bytes, bytes]:
    layout = pdf_layout or DEFAULT_BOT_LAYOUT
    assert_page2_fits(layout)
    png_display, _png_download = notebook_graphics_assets_fn(
        mode="cantilever",
        loads=loads,
        L=L,
        result=result,
        wide=wide_layout,
    )
    xs = np.asarray(result["xs"], dtype=float)
    normals = np.asarray(result["normal"], dtype=float)
    shears = np.asarray(result["shear"], dtype=float)
    moments = np.asarray(result["moment"], dtype=float)
    crit = cantilever_station_labels_fn(loads, L)
    forces_html = build_forces_diagram_html_fn(
        xs, normals, shears, moments, float(L), crit, wide=wide_layout, layout=layout
    )
    rows_pts = cantilever_values_at_stations_fn(loads, L, result)
    pts_html = point_calc_grid_html_fn(
        rows_pts,
        loads=loads,
        support_mode="cantilever",
        L=L,
        cantilever_result=result,
    )

    calc_html = notebook_calc_stub_under_beam_fn(
        loads,
        float(result.get("R_Ax", 0.0)),
        L=L,
        support_mode="cantilever",
        cantilever_result=result,
    )
    extra = build_bot_notebook_extra_html_fn(
        layout,
        calc_html=calc_html,
        forces_html=forces_html,
        point_calc_inner_html=pts_html,
    )
    body = notebook_graphics_html_fn(png_display, extra)
    pdf_bytes = html_to_pdf_bytes_fn(wrap_pdf_document_fn(body, wide=wide_layout))
    png_page = pdf_to_png_bytes_fn(pdf_bytes, dpi=export_dpi)
    return wrap_iframe_document_fn(body), png_page, pdf_bytes
