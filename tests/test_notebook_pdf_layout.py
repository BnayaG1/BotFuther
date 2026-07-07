# -*- coding: utf-8 -*-
"""Regression: חוזה פריסת PDF למחברת הבוט (2 עמודים, גרפים מלאים)."""
from __future__ import annotations

from dataclasses import replace

import fitz
import pytest

import beam_notebook as bn
import solver
from notebook_pdf_layout import DEFAULT_BOT_LAYOUT, assert_page2_fits, estimate_page2_height_mm


def _reference_loads():
    return [{"type": "point", "x": 3.0, "Fy": -10.0}]


def _build_reference_pdf():
    loads = _reference_loads()
    L = 6.0
    ra_pos, rb_pos = 0.0, L
    ra_x, ra_y, rb_x, rb_y = solver.compute_reactions(loads, L, ra_pos, rb_pos)
    _, _, pdf = bn.build_page_html(
        loads, L, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y, wide_layout=True
    )
    return pdf


def _force_images(doc: fitz.Document) -> list[tuple[int, float, float, float, float]]:
    """(page, y0, y1, width, height) for N/Q/M panels below the calc block."""
    out: list[tuple[int, float, float, float, float]] = []
    for pi in range(doc.page_count):
        for b in doc[pi].get_text("dict")["blocks"]:
            if b.get("type") != 1:
                continue
            x0, y0, x1, y1 = b["bbox"]
            w, h = x1 - x0, y1 - y0
            if 550 < w < 580 and h > 60 and y0 > 400:
                out.append((pi, y0, y1, w, h))
    out.sort(key=lambda t: (t[0], t[1]))
    return out[-3:]


def _text_max_y(page: fitz.Page) -> float:
    blocks = page.get_text("dict")["blocks"]
    texts = [b for b in blocks if b.get("type") == 0]
    if not texts:
        return 0.0
    return max(b["bbox"][3] for b in texts)


def _calc_to_n_gap_mm(page: fitz.Page) -> float:
    """Vertical gap between last calc line and top of N panel (mm)."""
    blocks = page.get_text("dict")["blocks"]
    texts = [b for b in blocks if b.get("type") == 0]
    forces = [
        b
        for b in blocks
        if b.get("type") == 1
        and 550 < (b["bbox"][2] - b["bbox"][0]) < 580
        and (b["bbox"][3] - b["bbox"][1]) > 60
        and b["bbox"][1] > 400
    ]
    if not texts or not forces:
        return 0.0
    calc_bottom = max(b["bbox"][3] for b in texts)
    n_top = min(b["bbox"][1] for b in forces)
    return (n_top - calc_bottom) * 25.4 / 72


def test_page2_height_fits_default_layout():
    est = estimate_page2_height_mm(DEFAULT_BOT_LAYOUT)
    avail = 297.0 - DEFAULT_BOT_LAYOUT.page_padding_top_mm - DEFAULT_BOT_LAYOUT.page_padding_bottom_mm
    assert est <= avail, f"page 2 estimate {est:.1f}mm > available {avail:.1f}mm"


def test_assert_page2_fits_no_warning():
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert_page2_fits(DEFAULT_BOT_LAYOUT)
    assert not caught


def test_bot_notebook_page_contract():
    pdf = _build_reference_pdf()
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        assert doc.page_count == 2, f"expected 2 pages, got {doc.page_count}"

        forces = _force_images(doc)
        assert len(forces) == 3, f"expected 3 force images, got {len(forces)}"

        for pi, y0, y1, w, h in forces:
            assert pi == 0, f"force image on page {pi}, expected page 0 (0-indexed)"
            assert w > 550, f"width {w:.0f}pt too narrow"
            assert h > 60, f"height {h:.0f}pt — graph may be clipped"

        gap_nq = forces[1][1] - forces[0][2]
        gap_qm = forces[2][1] - forces[1][2]
        assert gap_nq == pytest.approx(gap_qm, abs=3.0), (
            f"N→Q gap {gap_nq:.1f}pt != Q→M gap {gap_qm:.1f}pt"
        )

        calc_bottom = _text_max_y(doc[0])
        assert calc_bottom > 0

        calc_n_gap_mm = _calc_to_n_gap_mm(doc[0])
        assert calc_n_gap_mm == pytest.approx(20.4, abs=2.5), (
            f"calc→N gap {calc_n_gap_mm:.1f}mm, expected ~20mm"
        )

        pt_texts = [b for b in doc[1].get_text("dict")["blocks"] if b.get("type") == 0]
        assert pt_texts, "point calc should appear on page 2"
    finally:
        doc.close()


def test_bot_notebook_multi_load_two_pages():
    """Regression: heavier page-1 content must still paginate to point calc."""
    loads = [
        {"type": "point", "x": 2.0, "Fy": -5.0},
        {"type": "point", "x": 5.0, "Fy": -8.0},
        {"type": "udl", "x1": 1.0, "x2": 7.0, "Fy": -2.0},
    ]
    L = 8.0
    ra_pos, rb_pos = 0.0, L
    ra_x, ra_y, rb_x, rb_y = solver.compute_reactions(loads, L, ra_pos, rb_pos)
    _, _, pdf = bn.build_page_html(
        loads, L, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y, wide_layout=True
    )
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        assert doc.page_count == 2, f"expected 2 pages, got {doc.page_count}"
        forces = _force_images(doc)
        assert len(forces) == 3, f"expected 3 force images, got {len(forces)}"
        for pi, y0, y1, w, h in forces:
            assert pi == 0, f"force image on page {pi}, expected page 0"
            assert h > 60, f"height {h:.0f}pt — graph may be clipped"
        pt_texts = [b for b in doc[1].get_text("dict")["blocks"] if b.get("type") == 0]
        assert pt_texts, "point calc should appear on page 2"
    finally:
        doc.close()


    layout = replace(DEFAULT_BOT_LAYOUT, gap_q_to_m_squares=4)
    loads = _reference_loads()
    L = 6.0
    ra_pos, rb_pos = 0.0, L
    ra_x, ra_y, rb_x, rb_y = solver.compute_reactions(loads, L, ra_pos, rb_pos)
    _, _, pdf = bn.build_page_html(
        loads, L, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y,
        wide_layout=True, pdf_layout=layout,
    )
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        forces = _force_images(doc)
        gap_nq = forces[1][1] - forces[0][2]
        gap_qm = forces[2][1] - forces[1][2]
        assert gap_nq != pytest.approx(gap_qm, abs=3.0)
    finally:
        doc.close()
