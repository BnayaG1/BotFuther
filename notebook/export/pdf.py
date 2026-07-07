# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import os
import tempfile
from typing import Any

from notebook.constants import (
    _BOT_EXPORT_DPI,
    _GRID,
    _GRID_CELL_MM,
    _HEEBO_TTF,
    _PAPER,
    _FONT_DIR,
    _a4_content_rect,
)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _notebook_grid_png_path(width_pt: float, height_pt: float, *, dpi: int) -> str:
    """PNG זמני: נייר + משבצות ריבועיות לשכבת רקע ב-PDF (Story לא מצייר CSS grid)."""
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
    """מדביק רשת נייר מאחורי כל עמוד — PyMuPDF Story תומך רק ב-background-color."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page in doc:
            rect = page.rect
            gpath = _notebook_grid_png_path(rect.width, rect.height, dpi=dpi)
            try:
                page.insert_image(rect, filename=gpath, overlay=False)
            finally:
                os.unlink(gpath)
        return doc.tobytes()
    finally:
        doc.close()


def _html_to_pdf_bytes(html: str, *, ensure_notebook_font: Any) -> bytes:
    """דף מחברת מלא → PDF (רב־עמודי אם צריך)."""
    import fitz

    ensure_notebook_font()
    archive = fitz.Archive(str(_FONT_DIR)) if _HEEBO_TTF.is_file() else None
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    mediabox = fitz.Rect(0, 0, 595.28, 841.89)
    where = _a4_content_rect(mediabox)
    story = fitz.Story(html=html, archive=archive)
    while True:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
        if not more:
            break
    writer.close()
    return _stamp_notebook_grid_on_pdf(buf.getvalue())

