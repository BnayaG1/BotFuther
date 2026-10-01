# -*- coding: utf-8 -*-
"""כרטיסים חזותיים קצרים למבוא לסטטיקה."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_W, _H = 1200, 675
_BG = (244, 233, 209)
_GRID = (211, 194, 164)
_INK = (36, 44, 62)
_MUTED = (104, 112, 126)
_BLUE = (28, 92, 170)
_GREEN = (34, 132, 78)
_AMBER = (205, 126, 30)
_RED = (196, 60, 54)
_CARD = _BG
_LINE = _INK
_CELL = 24

_FONT_PATHS = (
    Path(__file__).resolve().parents[1] / ".notebook_fonts" / "Heebo-Regular.ttf",
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
    Path(r"C:\Windows\Fonts\arial.ttf"),
)
_MATH_FONT_PATHS = (
    Path(r"C:\Windows\Fonts\segoepr.ttf"),
    Path(r"C:\Windows\Fonts\Inkfree.ttf"),
    Path(r"C:\Windows\Fonts\comic.ttf"),
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
)


def generate_foundations_visual(page_id: str, out_dir: Path) -> Path | None:
    renderers = {
        "foundations_start": _draw_start,
        "foundations_concept": _draw_concept,
        "foundations_loads": _draw_loads_and_supports,
        "foundations_equilibrium": _draw_equilibrium,
        "foundations_workflow": _draw_workflow,
        "foundations_summary": _draw_workflow,
    }
    renderer = renderers.get(page_id)
    if renderer is None:
        return None
    image = _canvas()
    renderer(image)
    out_path = Path(out_dir) / f"{page_id}.png"
    image.save(out_path, "PNG")
    return out_path


def _canvas() -> Image.Image:
    image = Image.new("RGB", (_W, _H), _BG)
    draw = ImageDraw.Draw(image)
    for x in range(0, _W, _CELL):
        draw.line((x, 0, x, _H), fill=_GRID, width=1)
    for y in range(0, _H, _CELL):
        draw.line((0, y, _W, y), fill=_GRID, width=1)
    return image


def _font(size: int) -> ImageFont.ImageFont:
    path = next((path for path in _FONT_PATHS if path.is_file()), None)
    return ImageFont.truetype(str(path), size) if path else ImageFont.load_default()


def _math_font(size: int) -> ImageFont.ImageFont:
    path = next((path for path in _MATH_FONT_PATHS if path.is_file()), None)
    return ImageFont.truetype(str(path), size) if path else _font(size)


def _rtl(text: str) -> str:
    return text[::-1]


def _text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    size: int,
    *,
    fill: tuple[int, int, int] = _INK,
    anchor: str = "mm",
    rtl: bool = False,
    math: bool = False,
) -> None:
    font = _math_font(size) if math else _font(size)
    draw.text(xy, _rtl(text) if rtl else text, font=font, fill=fill, anchor=anchor)


def _title(draw: ImageDraw.ImageDraw, text: str) -> None:
    _text(draw, (_W / 2, 65), text, 42, rtl=True)
    _pen(draw, (500, 103), (700, 103), _BLUE, width=5)


def _rounded_card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    _pen(draw, (x0, y0), (x1, y0), _LINE, width=3)
    _pen(draw, (x1, y0), (x1, y1), _LINE, width=3)
    _pen(draw, (x1, y1), (x0, y1), _LINE, width=3)
    _pen(draw, (x0, y1), (x0, y0), _LINE, width=3)


def _pen(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    color: tuple[int, int, int] = _INK,
    *,
    width: int = 4,
) -> None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 2:
        draw.line((start, end), fill=color, width=width)
        return
    nx, ny = -dy / length, dx / length
    steps = max(5, int(length / 22))
    points = []
    for index in range(steps + 1):
        t = index / steps
        wave = math.sin(math.pi * t) * math.sin(index * 1.7 + start[0] * 0.03) * 1.2
        points.append((start[0] + dx * t + nx * wave, start[1] + dy * t + ny * wave))
    draw.line(points, fill=color, width=width, joint="curve")


def _arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    color: tuple[int, int, int],
    width: int = 7,
) -> None:
    _pen(draw, start, end, color, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    length = 20
    spread = 0.52
    left = (
        end[0] - length * math.cos(angle - spread),
        end[1] - length * math.sin(angle - spread),
    )
    right = (
        end[0] - length * math.cos(angle + spread),
        end[1] - length * math.sin(angle + spread),
    )
    draw.polygon((end, left, right), fill=color)


def _draw_start(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    _title(draw, "מפת הפתרון")
    labels = ("שרטוט", "עומסים", "משוואות", "בדיקה")
    colors = (_BLUE, _AMBER, _GREEN, _INK)
    for index, (label, color) in enumerate(zip(labels, colors), start=1):
        cx = 150 + (index - 1) * 300
        draw.ellipse((cx - 47, 220, cx + 47, 314), outline=color, width=5)
        _text(draw, (cx, 267), str(index), 42, fill=color, math=True)
        _text(draw, (cx, 390), label, 31, rtl=True)
        _pen(draw, (cx - 62, 425), (cx + 62, 425), color, width=3)
        if index < 4:
            _arrow(draw, (cx + 75, 267), (cx + 220, 267), _MUTED, width=4)


def _draw_concept(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    _title(draw, "מה מחפשים בתרגיל?")
    beam_y = 340
    _pen(draw, (170, beam_y), (1030, beam_y), _INK, width=12)
    _pin(draw, 270, beam_y)
    _roller(draw, 930, beam_y)
    _arrow(draw, (600, 165), (600, beam_y - 15), _RED)
    _arrow(draw, (270, 500), (270, beam_y + 18), _GREEN)
    _arrow(draw, (930, 500), (930, beam_y + 18), _GREEN)
    _text(draw, (620, 195), "P", 32, fill=_RED, anchor="lm", math=True)
    _text(draw, (245, 530), "RA", 30, fill=_GREEN, math=True)
    _text(draw, (955, 530), "RB", 30, fill=_GREEN, math=True)
    _text(draw, (600, 600), "RA + RB = P", 38, fill=_INK, math=True)


def _draw_loads_and_supports(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    _title(draw, "מזהים לפני שמחשבים")
    cards = ((55, 135, 365, 365), (445, 135, 755, 365), (835, 135, 1145, 365))
    labels = ("כוח נקודתי", "עומס מפורס", "כוח אלכסוני")
    for box, label in zip(cards, labels):
        _text(draw, ((box[0] + box[2]) / 2, 180), label, 26, rtl=True)

    for x0, x1 in ((105, 315), (495, 705), (885, 1095)):
        _pen(draw, (x0, 315), (x1, 315), _INK, width=7)
    _arrow(draw, (210, 220), (210, 300), _RED)
    for x in (530, 575, 620, 665):
        _arrow(draw, (x, 220), (x, 300), _AMBER, width=5)
    _pen(draw, (530, 220), (665, 220), _AMBER, width=5)
    _arrow(draw, (980, 215), (930, 300), _BLUE)
    _pen(draw, (980, 215), (980, 300), _MUTED, width=2)
    _pen(draw, (930, 300), (980, 300), _MUTED, width=2)
    _text(draw, (1000, 258), "Fy", 24, fill=_BLUE, anchor="lm", math=True)
    _text(draw, (950, 325), "Fx", 24, fill=_BLUE, math=True)

    _text(draw, (160, 430), "1", 30, fill=_MUTED)
    _roller(draw, 160, 470)
    _text(draw, (160, 585), "נייד", 25, rtl=True)
    _text(draw, (600, 430), "2", 30, fill=_MUTED)
    _pin(draw, 600, 470)
    _text(draw, (600, 585), "צירי", 25, rtl=True)
    _text(draw, (1040, 430), "3", 30, fill=_MUTED)
    _fixed(draw, 1040, 470)
    _text(draw, (1040, 585), "ריתום", 25, rtl=True)


def _draw_equilibrium(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    _title(draw, "שלוש משוואות")
    equations = (("ΣFx = 0", _BLUE), ("ΣFy = 0", _GREEN), ("ΣM = 0", _AMBER))
    for index, (equation, color) in enumerate(equations):
        cx = 225 + index * 375
        _text(draw, (cx, 235), equation, 49, fill=color, math=True)
        _pen(draw, (cx - 105, 285), (cx + 105, 285), color, width=4)
    _pen(draw, (260, 500), (940, 500), _INK, width=8)
    draw.ellipse((245, 485, 275, 515), fill=_INK)
    _arrow(draw, (760, 390), (760, 485), _RED)
    _pen(draw, (260, 550), (760, 550), _MUTED, width=3)
    _pen(draw, (260, 535), (260, 565), _MUTED, width=3)
    _pen(draw, (760, 535), (760, 565), _MUTED, width=3)
    _text(draw, (510, 580), "d", 28, fill=_MUTED, math=True)
    _text(draw, (785, 420), "F", 28, fill=_RED, anchor="lm", math=True)
    _text(draw, (975, 520), "M = F · d", 34, fill=_INK, math=True)


def _draw_workflow(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    _title(draw, "סדר עבודה במבחן")
    steps = (
        ("1", "שרטוט", "FBD"),
        ("2", "הכנה", "Fx  Fy"),
        ("3", "פתרון", "ΣM = 0"),
        ("4", "בדיקה", "ΣF = 0"),
    )
    colors = (_BLUE, _AMBER, _GREEN, _INK)
    for index, ((number, label, formula), color) in enumerate(zip(steps, colors)):
        cx = 150 + index * 300
        draw.ellipse((cx - 37, 180, cx + 37, 254), outline=color, width=5)
        _text(draw, (cx, 217), number, 34, fill=color, math=True)
        _text(draw, (cx, 325), label, 30, rtl=True)
        _text(draw, (cx, 420), formula, 31, fill=color, math=True)
        _pen(draw, (cx - 62, 465), (cx + 62, 465), color, width=3)
        if index < 3:
            _arrow(draw, (cx + 75, 300), (cx + 220, 300), _MUTED, width=4)


def _pin(draw: ImageDraw.ImageDraw, x: float, beam_y: float) -> None:
    top = beam_y + 8
    _pen(draw, (x, top), (x - 34, top + 58), _INK, width=4)
    _pen(draw, (x - 34, top + 58), (x + 34, top + 58), _INK, width=4)
    _pen(draw, (x + 34, top + 58), (x, top), _INK, width=4)
    _pen(draw, (x - 48, top + 64), (x + 48, top + 64), _INK, width=4)


def _roller(draw: ImageDraw.ImageDraw, x: float, beam_y: float) -> None:
    top = beam_y + 8
    _pen(draw, (x, top), (x - 32, top + 48), _INK, width=4)
    _pen(draw, (x - 32, top + 48), (x + 32, top + 48), _INK, width=4)
    _pen(draw, (x + 32, top + 48), (x, top), _INK, width=4)
    for dx in (-18, 18):
        draw.ellipse((x + dx - 8, top + 49, x + dx + 8, top + 65), outline=_INK, width=4)
    _pen(draw, (x - 50, top + 72), (x + 50, top + 72), _INK, width=4)


def _fixed(draw: ImageDraw.ImageDraw, x: float, beam_y: float) -> None:
    _pen(draw, (x, beam_y - 45), (x, beam_y + 75), _INK, width=8)
    for offset in range(-40, 75, 18):
        _pen(draw, (x, beam_y + offset), (x + 30, beam_y + offset + 18), _MUTED, width=3)
    _pen(draw, (x - 95, beam_y), (x, beam_y), _INK, width=8)

