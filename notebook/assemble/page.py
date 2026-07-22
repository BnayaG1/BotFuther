# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, List, Optional, Tuple

import numpy as np

import core.statics_calculator as solver
from notebook.pdf_layout import DEFAULT_BOT_LAYOUT, NotebookPdfLayout, assert_page2_fits


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
    # injected deps to avoid circular imports
    notebook_graphics_assets_fn: Any,
    station_labels_fn: Any,
    build_forces_diagram_html_fn: Any,
    values_at_stations_fn: Any,
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
    png_display, png_download = notebook_graphics_assets_fn(
        mode="supports",
        loads=loads,
        L=L,
        ra_pos=ra_pos,
        rb_pos=rb_pos,
        ra_x=ra_x,
        ra_y=ra_y,
        rb_x=rb_x,
        rb_y=rb_y,
        wide=wide_layout,
    )
    positions = solver.critical_x_positions(loads, L, ra_pos, rb_pos)
    xs = solver.beam_plot_x_coords(L, positions)
    moments = np.array([solver.bending_moment(x, loads, ra_y, rb_y, ra_pos, rb_pos) for x in xs])
    shears = np.array([solver.shear_force(x, loads, ra_y, rb_y, ra_pos, rb_pos) for x in xs])
    normals = np.array([solver.normal_force(x, loads, ra_x, ra_pos) for x in xs])
    crit = station_labels_fn(loads, L, ra_pos, rb_pos)
    forces_html = build_forces_diagram_html_fn(
        xs, normals, shears, moments, float(L), crit, wide=wide_layout, layout=layout
    )
    rows_pts = values_at_stations_fn(loads, L, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y)
    pts_html = point_calc_grid_html_fn(
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

    calc_html = notebook_calc_stub_under_beam_fn(
        loads,
        ra_x,
        support_mode="supports",
        ra_pos=ra_pos,
        rb_pos=rb_pos,
        ra_y=ra_y,
        rb_y=rb_y,
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

