# -*- coding: utf-8 -*-
"""דף מחברת אחד — שטח של שני A4, בלי האורך שלהם זה מעל זה."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw

# A3 לרוחב: 420×297 מ"מ. אותו שטח כמו שני A4 עומדים (210×594), כחצי הגובה.
PAGE_W_MM = 420.0
PAGE_H_MM = 297.0
EXPORT_DPI = 150

# משבצת ~2.9 מ"מ, כמו בדף הישן. הגודל בפיקסלים מתחלק בה בלי שארית.
_CELL_PX = 17

_PAPER = (241, 226, 196)
_GRID = (201, 184, 154)


def page_pixel_size() -> tuple[int, int]:
    """רוחב וגובה בפיקסלים, מיושרים למשבצות."""
    raw_w = PAGE_W_MM / 25.4 * EXPORT_DPI
    raw_h = PAGE_H_MM / 25.4 * EXPORT_DPI
    width = int(round(raw_w / _CELL_PX) * _CELL_PX)
    height = int(round(raw_h / _CELL_PX) * _CELL_PX)
    return width, height


def new_page() -> Image.Image:
    """דף ריק: נייר מיושן ורשת משבצות."""
    width, height = page_pixel_size()
    image = Image.new("RGB", (width, height), _PAPER)
    draw = ImageDraw.Draw(image)
    for x in range(0, width, _CELL_PX):
        draw.line([(x, 0), (x, height)], fill=_GRID, width=1)
    for y in range(0, height, _CELL_PX):
        draw.line([(0, y), (width, y)], fill=_GRID, width=1)
    return image


def image_to_png(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG", dpi=(EXPORT_DPI, EXPORT_DPI))
    return buf.getvalue()


def render_blank_page_png() -> bytes:
    return image_to_png(new_page())
