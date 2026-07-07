# -*- coding: utf-8 -*-
from __future__ import annotations

import io
from typing import Any, List

from notebook.constants import _EMBED_DPI, _EXPORT_DPI, _PAPER


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


def _fig_to_png_bytes(
    fig: Any,
    *,
    prep_figure_notebook_paper: Any,
    style: str = "embed",
    pad_inches: float = 0.02,
    bbox: str = "tight",
) -> bytes:
    """
    style='embed' — PNG שקוף (תצוגת iframe ישנה).
    style='paper' — נייר מחברת + רשת, להטמעה בדף משבצות.
    style='export' — נייר מחברת + רשת, dpi גבוה (ייצוא עצמאי).
    bbox='figure' — גודל קבוע (דיאגרמות N/Q/M); 'tight' — חיתוך לתוכן.
    """
    buf = io.BytesIO()
    bbox_inches = None if bbox == "figure" else "tight"
    if style in ("export", "paper"):
        prep_figure_notebook_paper(fig)
        fig.savefig(
            buf,
            format="png",
            dpi=_EXPORT_DPI if style == "export" else _EMBED_DPI,
            transparent=False,
            facecolor=_PAPER,
            edgecolor=_PAPER,
            bbox_inches=bbox_inches,
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
            bbox_inches=bbox_inches,
            pad_inches=pad_inches,
        )
    buf.seek(0)
    return buf.getvalue()

