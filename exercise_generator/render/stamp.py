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
    text = style.STAMP_TEXT
    # Pillow מצייר LTR — הופכים לתצוגה עברית נכונה
    text_draw = text[::-1]
    font = _hebrew_font(34)

    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text_draw, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    # ברקוד קומפקטי מעל הטקסט
    barcode_w = max(90, int(tw * 0.85))
    ratio = barcode_w / max(barcode.width, 1)
    barcode_h = max(1, int(barcode.height * ratio))
    barcode = barcode.resize((barcode_w, barcode_h), Image.Resampling.LANCZOS)

    gap = 6
    pad = 4
    total_w = max(barcode_w, tw) + 2 * pad
    total_h = pad + barcode_h + gap + th + pad
    canvas = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    canvas.paste(barcode, ((total_w - barcode_w) // 2, pad))

    draw = ImageDraw.Draw(canvas)
    tx = (total_w - tw) // 2 - bbox[0]
    ty = pad + barcode_h + gap - bbox[1]
    ink = (*style.STAMP_INK_RGB, 255)
    draw.text((tx, ty), text_draw, font=font, fill=ink)
    return canvas


def draw_brand_stamp(canvas: Canvas) -> None:
    """מציב את חותמת המותג בפינה הימנית-עליונה של ה־figure."""
    stamp = _compose_stamp_rgba()
    if stamp is None:
        return

    fig = canvas.fig
    fig_w_px = int(fig.get_figwidth() * style.DPI)
    target_w = max(48, int(fig_w_px * style.STAMP_WIDTH_FRAC))
    ratio = target_w / max(stamp.width, 1)
    target_h = max(1, int(stamp.height * ratio))
    stamp = stamp.resize((target_w, target_h), Image.Resampling.LANCZOS)

    pad_x = int(fig_w_px * style.STAMP_PAD_FRAC)
    fig_h_px = int(fig.get_figheight() * style.DPI)
    pad_y = int(fig_h_px * style.STAMP_PAD_FRAC)
    # figimage: xo/yo מפינה תחתונה-שמאלית
    xo = fig_w_px - target_w - pad_x
    yo = fig_h_px - target_h - pad_y
    fig.figimage(
        np.asarray(stamp),
        xo=max(0, xo),
        yo=max(0, yo),
        zorder=20,
    )
