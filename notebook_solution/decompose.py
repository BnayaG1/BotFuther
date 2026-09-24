# -*- coding: utf-8 -*-
"""פירוק עומסים אלכסוניים ומפורסים — סוגריים בפינה הימנית העליונה."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

from notebook_solution.page import _CELL_PX, page_pixel_size
from notebook_solution.problem import LoadMark, Problem
from notebook_solution.sketch import _FONT_FILES, _INK, _arrow, _fmt, _pen

_ROW_H = 46
_PAD_X = 22
_PAD_Y = 14


def draw_decomposition(image: Image.Image, problem: Problem) -> None:
    rows = _rows(problem)
    if not rows:
        return
    draw = ImageDraw.Draw(image)
    fonts = _fonts()
    page_w, _ = page_pixel_size()
    right = page_w - _CELL_PX * 4
    top = _CELL_PX * 3
    widths = [_row_width(draw, row, fonts) for row in rows]
    inner_w = max(widths)
    left = right - inner_w - 2 * _PAD_X
    height = len(rows) * _ROW_H
    y0 = top
    y1 = top + height + 2 * _PAD_Y
    _brackets(draw, left, right, y0, y1)
    for i, row in enumerate(rows):
        y = y0 + _PAD_Y + i * _ROW_H + _ROW_H / 2
        _draw_row(draw, left + _PAD_X, y, row, fonts)


def _rows(problem: Problem) -> list[dict]:
    inclined = [ld for ld in problem.loads if ld.kind == "inclined"]
    distributed = [ld for ld in problem.loads if ld.kind == "distributed"]
    inclined.sort(key=lambda ld: ld.x)
    distributed.sort(key=lambda ld: ld.x1)
    rows: list[dict] = []
    number_inclined = len(inclined) > 1
    for i, load in enumerate(inclined):
        mag = _fmt(load.magnitude)
        ang = _fmt(load.angle_deg)
        rad = math.radians(abs(load.angle_deg))
        fy = abs(load.magnitude * math.sin(rad))
        fx = abs(load.magnitude * math.cos(rad))
        prefix = f"{mag}t = "
        mark = str(i + 1) if number_inclined else ""
        rows.append(
            {
                "kind": "inclined",
                "lead": True,
                "mark": mark,
                "load": load,
                "prefix": prefix,
                "eq": f"{mag} × sin({ang}°) = {_fmt(fy)}t (",
                "arrow": "down",
            }
        )
        rows.append(
            {
                "kind": "inclined",
                "lead": False,
                "mark": "",
                "load": load,
                "prefix": prefix,
                "eq": f"{mag} × cos({ang}°) = {_fmt(fx)}t (",
                "arrow": "right" if load.incl_dir == "dr" else "left",
            }
        )
    for load in distributed:
        span = abs(load.x2 - load.x1)
        w1, w2 = abs(load.w1), abs(load.w2)
        if abs(w1 - w2) < 1e-9:
            force = w1 * span
            eq = f"{_fmt(w1)} × {_fmt(span)}"
            weight = f"{_fmt(w1)}tm"
        else:
            force = (w1 + w2) / 2.0 * span
            eq = f"({_fmt(w1)} + {_fmt(w2)}) / 2 × {_fmt(span)}"
            weight = f"{_fmt(max(w1, w2))}tm"
        rows.append(
            {
                "kind": "distributed",
                "lead": True,
                "mark": "",
                "load": load,
                "prefix": f"{weight} = ",
                "eq": f"{eq} = {_fmt(force)}t",
            }
        )
    return rows


def _fonts() -> dict[str, ImageFont.ImageFont]:
    path = next((item for item in _FONT_FILES if item.is_file()), None)
    if path is None:
        base = ImageFont.load_default()
        return {"text": base, "sub": base}
    return {
        "text": ImageFont.truetype(str(path), 26),
        "sub": ImageFont.truetype(str(path), 16),
    }


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> float:
    box = draw.textbbox((0, 0), text, font=font)
    return float(box[2] - box[0])


_ARROW_SLOT = 22


def _row_width(draw: ImageDraw.ImageDraw, row: dict, fonts: dict) -> float:
    extra = _ARROW_SLOT + _text_w(draw, ")", fonts["text"]) if row.get("arrow") else 0
    return 36.0 + _text_w(draw, row["prefix"] + row["eq"], fonts["text"]) + extra


def _draw_row(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    row: dict,
    fonts: dict,
) -> None:
    font = fonts["text"]
    text_x = x + 38
    prefix_w = _text_w(draw, row["prefix"], font)
    if row["kind"] == "inclined":
        if row["lead"]:
            _inclined_mark(draw, x + 10, y, row["load"])
            if row["mark"]:
                draw.text((x + 22, y + 10), row["mark"], font=fonts["sub"], fill=_INK, anchor="mm")
            draw.text((text_x, y), row["prefix"], font=font, fill=_INK, anchor="lm")
        eq_x = text_x + prefix_w
        draw.text((eq_x, y), row["eq"], font=font, fill=_INK, anchor="lm")
        if row.get("arrow"):
            ax = eq_x + _text_w(draw, row["eq"], font) + 11
            _dir_arrow(draw, ax, y, row["arrow"])
            draw.text((ax + 12, y), ")", font=font, fill=_INK, anchor="lm")
        return
    _distributed_mark(draw, x + 14, y)
    draw.text((text_x, y), row["prefix"] + row["eq"], font=font, fill=_INK, anchor="lm")


def _dir_arrow(draw: ImageDraw.ImageDraw, x: float, y: float, direction: str) -> None:
    if direction == "down":
        _arrow(draw, (x, y - 8), (x, y + 8), width=2)
    elif direction == "left":
        _arrow(draw, (x + 8, y), (x - 8, y), width=2)
    else:
        _arrow(draw, (x - 8, y), (x + 8, y), width=2)


def _inclined_mark(draw: ImageDraw.ImageDraw, x: float, y: float, load: LoadMark) -> None:
    angle = math.radians(max(20.0, min(70.0, abs(load.angle_deg))))
    length = 22
    sign = 1.0 if load.incl_dir == "dr" else -1.0
    dx = sign * length * math.cos(angle)
    dy = -length * math.sin(angle)
    _arrow(draw, (x - dx * 0.45, y + dy * 0.45), (x + dx * 0.55, y - dy * 0.55), width=2)


def _distributed_mark(draw: ImageDraw.ImageDraw, x: float, y: float) -> None:
    top = y - 12
    bot = y + 10
    _pen(draw, (x - 12, top), (x + 12, top), width=2)
    for dx in (-8, 0, 8):
        _arrow(draw, (x + dx, top), (x + dx, bot), width=1)


def _brackets(draw: ImageDraw.ImageDraw, left: float, right: float, y0: float, y1: float) -> None:
    hook = 12
    _pen(draw, (left + hook, y0), (left, y0), width=2)
    _pen(draw, (left, y0), (left, y1), width=2)
    _pen(draw, (left, y1), (left + hook, y1), width=2)
    _pen(draw, (right - hook, y0), (right, y0), width=2)
    _pen(draw, (right, y0), (right, y1), width=2)
    _pen(draw, (right, y1), (right - hook, y1), width=2)
