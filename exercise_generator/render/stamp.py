# -*- coding: utf-8 -*-
"""חותמת מותג בפינה הימנית-עליונה של תרגיל PNG."""
from __future__ import annotations

import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from exercise_generator.render.canvas import Canvas
from exercise_generator.render import style

_PKG_ROOT = Path(__file__).resolve().parent.parent


def _barcode_path() -> Path:
    return _PKG_ROOT / style.STAMP_BARCODE_RELATIVE


def _hebrew_font(size: int) -> ImageFont.ImageFont:
    """פונט מערכת עם תמיכה בעברית (Windows / נפילה ל־default)."""
    candidates = [
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\david.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _fit_hebrew(text_draw: str, max_w: int) -> tuple[ImageFont.ImageFont, tuple[int, int, int, int], int, int]:
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    size = 40
    font = _hebrew_font(size)
    bbox = probe.textbbox((0, 0), text_draw, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    while size > 12 and tw > max_w:
        size -= 1
        font = _hebrew_font(size)
        bbox = probe.textbbox((0, 0), text_draw, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    return font, bbox, tw, th


@lru_cache(maxsize=1)
def _compose_stamp_rgba() -> Image.Image | None:
    barcode_path = _barcode_path()
    if not barcode_path.is_file():
        warnings.warn(
            f"stamp barcode missing: {barcode_path}",
            stacklevel=2,
        )
        return None

    barcode = Image.open(barcode_path).convert("RGBA")
    # המקור הוא פיקסל אחד למודול. מגדילים רק בכפולה שלמה כדי שהקצוות יישארו חדים.
    module_px = max(barcode.width, 1)
    fig_w_px = int(style.FIG_WIDTH_IN * style.DPI)
    target = max(module_px, int(fig_w_px * style.STAMP_WIDTH_FRAC))
    scale = max(1, round(target / module_px))
    barcode = barcode.resize(
        (barcode.width * scale, barcode.height * scale),
        Image.Resampling.NEAREST,
    )

    text_draw = style.STAMP_TEXT[::-1]
    font, bbox, tw, th = _fit_hebrew(text_draw, barcode.width)
    gap = 6
    pad = 4
    total_w = max(barcode.width, tw) + 2 * pad
    total_h = pad + barcode.height + gap + th + pad
    canvas = Image.new("RGBA", (total_w, total_h), (255, 255, 255, 255))
    canvas.paste(barcode, ((total_w - barcode.width) // 2, pad))

    draw = ImageDraw.Draw(canvas)
    tx = (total_w - tw) // 2 - bbox[0]
    ty = pad + barcode.height + gap - bbox[1]
    draw.text((tx, ty), text_draw, font=font, fill=(*style.STAMP_INK_RGB, 255))
    return canvas


def draw_brand_stamp(canvas: Canvas) -> None:
    """מציב את חותמת המותג בפינה הימנית-עליונה של ה־figure."""
    stamp = _compose_stamp_rgba()
    if stamp is None:
        return

    fig = canvas.fig
    fig_w_px = int(fig.get_figwidth() * style.DPI)
    fig_h_px = int(fig.get_figheight() * style.DPI)
    pad_x = int(fig_w_px * style.STAMP_PAD_FRAC)
    pad_y = int(fig_h_px * style.STAMP_PAD_FRAC)
    # figimage: xo/yo מפינה תחתונה-שמאלית
    xo = fig_w_px - stamp.width - pad_x
    yo = fig_h_px - stamp.height - pad_y
    fig.figimage(
        np.asarray(stamp),
        xo=max(0, xo),
        yo=max(0, yo),
        zorder=20,
    )
