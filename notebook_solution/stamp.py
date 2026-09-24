# -*- coding: utf-8 -*-
"""חותמת מותג בפינה הימנית-תחתונה של דף המחברת."""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from exercise_generator.render import style
from exercise_generator.render.stamp import _barcode_path, _fit_hebrew
from notebook_solution.page import _CELL_PX, page_pixel_size

_QR_SCALE = 5
_FADE_PX = _CELL_PX * 2


@lru_cache(maxsize=1)
def _notebook_stamp() -> Image.Image | None:
    path = _barcode_path()
    if not path.is_file():
        return None
    qr = Image.open(path).convert("RGBA")
    qr = qr.resize((qr.width * _QR_SCALE, qr.height * _QR_SCALE), Image.Resampling.NEAREST)
    faded = _white_fade(qr, _FADE_PX)
    text_draw = style.STAMP_TEXT[::-1]
    font, bbox, tw, th = _fit_hebrew(text_draw, qr.width)
    gap = 8
    width = max(faded.width, tw + 8)
    height = faded.height + gap + th
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.paste(faded, ((width - faded.width) // 2, 0), faded)
    draw = ImageDraw.Draw(canvas)
    tx = (width - tw) // 2 - bbox[0]
    ty = faded.height + gap - bbox[1]
    draw.text((tx, ty), text_draw, font=font, fill=(*style.STAMP_INK_RGB, 255))
    return canvas


def _white_fade(qr: Image.Image, fade: int) -> Image.Image:
    """רקע לבן אטום על ה-QR, ומסביבו לבן שדוהה לשקיפות."""
    w, h = qr.size
    arr = np.zeros((h + 2 * fade, w + 2 * fade, 4), dtype=np.uint8)
    yy, xx = np.ogrid[: arr.shape[0], : arr.shape[1]]
    x0, y0, x1, y1 = fade, fade, fade + w, fade + h
    dx = np.maximum(np.maximum(x0 - xx, xx - (x1 - 1)), 0).astype(np.float32)
    dy = np.maximum(np.maximum(y0 - yy, yy - (y1 - 1)), 0).astype(np.float32)
    dist = np.sqrt(dx * dx + dy * dy)
    t = np.clip(dist / max(fade, 1), 0.0, 1.0)
    smooth = t * t * (3.0 - 2.0 * t)
    halo = dist > 0
    arr[halo, 0:3] = 255
    arr[halo, 3] = ((1.0 - smooth) * 255).astype(np.uint8)[halo]
    canvas = Image.fromarray(arr, "RGBA")
    canvas.paste(qr, (fade, fade), qr)
    return canvas


def paste_brand_stamp(image: Image.Image) -> None:
    """מדביק את החותמת לפינה הימנית-תחתונה, בלי מלבן לבן קשיח."""
    stamp = _notebook_stamp()
    if stamp is None:
        return
    page_w, page_h = page_pixel_size()
    margin = _CELL_PX
    x = page_w - stamp.width - margin
    y = page_h - stamp.height - margin
    base = image.convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(stamp, (max(0, x), max(0, y)), stamp)
    image.paste(Image.alpha_composite(base, layer).convert("RGB"))
