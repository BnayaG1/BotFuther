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


def _spider_path() -> Path:
    return _PKG_ROOT / style.STAMP_SPIDER_RELATIVE


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


def _recolor_rgba_ink(img: Image.Image, rgb: tuple[int, int, int]) -> Image.Image:
    """צובע פיקסלים אטומים בצבע הדיו; שומר אלפא."""
    arr = np.asarray(img).copy()
    r, g, b = rgb
    opaque = arr[:, :, 3] > 0
    arr[opaque, 0] = r
    arr[opaque, 1] = g
    arr[opaque, 2] = b
    return Image.fromarray(arr, mode="RGBA")


@lru_cache(maxsize=1)
def _compose_stamp_rgba() -> Image.Image | None:
    spider_path = _spider_path()
    if not spider_path.is_file():
        warnings.warn(
            f"stamp spider missing: {spider_path}",
            stacklevel=2,
        )
        return None

    spider = _recolor_rgba_ink(
        Image.open(spider_path).convert("RGBA"),
        style.STAMP_INK_RGB,
    )
    text = style.STAMP_TEXT
    # Pillow מצייר LTR — הופכים לתצוגה עברית נכונה
    text_draw = text[::-1]
    font = _hebrew_font(34)

    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text_draw, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    # עכביש קומפקטי מעל הטקסט
    spider_w = max(90, int(tw * 0.85))
    ratio = spider_w / max(spider.width, 1)
    spider_h = max(1, int(spider.height * ratio))
    spider = spider.resize((spider_w, spider_h), Image.Resampling.LANCZOS)

    gap = 6
    pad = 4
    total_w = max(spider_w, tw) + 2 * pad
    total_h = pad + spider_h + gap + th + pad
    canvas = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    canvas.paste(spider, ((total_w - spider_w) // 2, pad), spider)

    draw = ImageDraw.Draw(canvas)
    tx = (total_w - tw) // 2 - bbox[0]
    ty = pad + spider_h + gap - bbox[1]
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
