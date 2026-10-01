# -*- coding: utf-8 -*-
"""דף מחברת של פתרון מרכז כובד — שרטוט עם צירים, טבלת הנתונים ונוסחאות.

הדף כולל את כל תהליך הכיתה: מרכז כובד גלובלי (Cx, Cy) ומומנטי האינרציה
סביב הצירים המרכזיים בשטיינר (Ixx, Iyy).
"""
from __future__ import annotations

from pathlib import Path

from PIL import ImageDraw, ImageFont

from exercise_generator.center_of_gravity.generator import CogExercise, Component
from exercise_generator.center_of_gravity.render import _outline
from exercise_generator.center_of_gravity.solve import (
    CogSolution,
    component_global_centroid,
    solve_cog_exercise,
)
from notebook_solution.page import _CELL_PX, image_to_png, new_page
from notebook_solution.sketch import (
    _FONT_FILES,
    _INK,
    _arrow,
    _pen,
    draw_notebook_text,
    notebook_text_width,
)
from notebook_solution.stamp import paste_brand_stamp

_FILL = (212, 199, 172)
_PAPER = (241, 226, 196)

# Ink Free ראשון — הוא הפונט של דף הנוסחאות, ויש בו גם הסימן ⁴.
_PAGE_FONTS = (Path(r"C:\Windows\Fonts\Inkfree.ttf"), *_FONT_FILES)

_SKETCH_X0 = _CELL_PX * 4
_SKETCH_X1 = _CELL_PX * 42
_SKETCH_TOP = _CELL_PX * 43
_SKETCH_BOTTOM = _CELL_PX * 74
_SKETCH_SIDE_PAD = 150
_LEGEND_TOP = _CELL_PX * 79
_LEGEND_LINE_H = 58

_TABLE_X = _CELL_PX * 4
_TABLE_Y = _CELL_PX * 6
_COL_WIDTHS = (120, 250, 200, 200, 280, 280, 270, 270, 210, 210)
_ROW_H = 104

_FORMULA_X = _CELL_PX * 47
_FORMULA_MAX_X = _CELL_PX * 128  # שמאלה מחותמת המותג שבפינה התחתונה
_CX_BAR_Y = _CELL_PX * 48
_CY_BAR_Y = _CELL_PX * 58
_IXX_TOP_Y = _CELL_PX * 66
_IYY_TOP_Y = _CELL_PX * 84
_INERTIA_LINE_H = 95
_INERTIA_INDENT = 70


def render_cog_solution_png(exercise: CogExercise) -> bytes:
    """PNG של דף מחברת אחד עם כל תהליך הפתרון."""
    solution = solve_cog_exercise(exercise)
    image = new_page()
    draw = ImageDraw.Draw(image)
    fonts = _fonts()
    _draw_table(draw, solution, fonts)
    _draw_sketch(draw, exercise, solution, fonts)
    _draw_centroid_formulas(draw, solution, fonts)
    _draw_inertia_formulas(draw, solution, fonts)
    paste_brand_stamp(image)
    return image_to_png(image)


def _font_path() -> Path | None:
    return next((item for item in _PAGE_FONTS if item.is_file()), None)


def _fonts() -> dict[str, ImageFont.ImageFont]:
    path = _font_path()
    if path is None:
        base = ImageFont.load_default()
        return {"head": base, "cell": base, "legend": base, "mark": base, "math": base}
    return {
        "head": ImageFont.truetype(str(path), 38),
        "cell": ImageFont.truetype(str(path), 36),
        "legend": ImageFont.truetype(str(path), 34),
        "mark": ImageFont.truetype(str(path), 30),
        "math": ImageFont.truetype(str(path), 44),
    }


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: float,
    fallback: ImageFont.ImageFont,
) -> ImageFont.ImageFont:
    """הפונט הגדול ביותר שבו השורה עוד נכנסת לרוחב שנשאר."""
    path = _font_path()
    if path is None:
        return fallback
    for size in (44, 40, 36, 32, 30, 28):
        font = ImageFont.truetype(str(path), size)
        if _text_w(draw, text, font) <= max_width:
            return font
    return ImageFont.truetype(str(path), 26)


def _fmt(value: float, decimals: int = 2) -> str:
    rounded = round(float(value), decimals)
    if abs(rounded) < 10 ** -decimals:
        rounded = 0.0
    if abs(rounded - round(rounded)) < 10 ** -decimals:
        return f"{int(round(rounded)):,}"
    return f"{rounded:,.{decimals}f}"


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> float:
    return notebook_text_width(draw, text, font)


def _ink(draw, xy, text, font, anchor, fill=_INK) -> None:
    draw_notebook_text(draw, xy, text, font, fill, anchor)


# ---------- שרטוט החתך ----------

def _world_points(comp: Component) -> list[tuple[float, float]]:
    points = []
    for x, y in _outline(comp):
        wx = comp.width - x if comp.mirror else x
        points.append((comp.x + wx, comp.y + y))
    return points


def _draw_sketch(
    draw: ImageDraw.ImageDraw,
    exercise: CogExercise,
    solution: CogSolution,
    fonts: dict,
) -> None:
    comps = exercise.components
    min_x = min(c.x for c in comps)
    max_x = max(c.right for c in comps)
    min_y = min(c.y for c in comps)
    max_y = max(c.top for c in comps)
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)

    avail_w = (_SKETCH_X1 - _SKETCH_X0) - _SKETCH_SIDE_PAD
    avail_h = _SKETCH_BOTTOM - _SKETCH_TOP
    scale = min(avail_w / span_x, avail_h / span_y)

    left = _SKETCH_X0 + 110
    bottom = _SKETCH_TOP + (avail_h + span_y * scale) / 2.0

    def at(x: float, y: float) -> tuple[float, float]:
        return left + (x - min_x) * scale, bottom - (y - min_y) * scale

    for comp in comps:
        _draw_component(draw, comp, at)

    origin_px, origin_py = at(solution.origin_x, min_y)
    top_py = at(0.0, max_y)[1]
    axis_end = min(left + span_x * scale + 60, _SKETCH_X1)
    _arrow(draw, (origin_px - 60, origin_py), (axis_end, origin_py), width=2)
    _ink(draw, (axis_end + 14, origin_py), "X", font=fonts["head"], fill=_INK, anchor="lm")
    _arrow(draw, (origin_px, origin_py + 46), (origin_px, top_py - 60), width=2)
    _ink(draw, (origin_px - 20, top_py - 74), "Y", font=fonts["head"], fill=_INK, anchor="rm")

    total_area = 0.0
    moment_x = 0.0
    moment_y = 0.0
    for row, comp in zip(solution.rows, comps):
        area, gx, gy = component_global_centroid(comp)
        total_area += area
        moment_x += area * gx
        moment_y += area * gy
        cx_px, cy_px = at(gx, gy)
        _mark(draw, cx_px, cy_px, str(row.index), fonts["mark"])

    centre = at(moment_x / total_area, moment_y / total_area)
    _draw_centroid_axes(draw, centre, fonts, axis_end, top_py, origin_py)

    legend_y = _LEGEND_TOP
    for row in solution.rows:
        _ink(draw, 
            (_SKETCH_X0 + 20, legend_y),
            f"{row.index} - {row.label}",
            font=fonts["legend"],
            fill=_INK,
            anchor="lm",
        )
        legend_y += _LEGEND_LINE_H


def _draw_centroid_axes(
    draw: ImageDraw.ImageDraw,
    centre: tuple[float, float],
    fonts: dict,
    axis_end: float,
    top_py: float,
    base_py: float,
) -> None:
    """מרכז הכובד הגלובלי והצירים המרכזיים xx, yy — עליהם מחושבים Ixx, Iyy."""
    cx_px, cy_px = centre
    _pen(draw, (cx_px - 130, cy_px), (axis_end, cy_px), width=1)
    _ink(draw, (axis_end + 14, cy_px), "xx", font=fonts["legend"], fill=_INK, anchor="lm")
    _pen(draw, (cx_px, top_py - 50), (cx_px, base_py + 40), width=1)
    _ink(draw, (cx_px + 30, top_py - 44), "yy", font=fonts["legend"], fill=_INK, anchor="lm")
    _cross(draw, cx_px, cy_px)
    _ink(draw, (cx_px + 26, cy_px - 34), "C", font=fonts["head"], fill=_INK, anchor="lm")


def _cross(draw: ImageDraw.ImageDraw, x: float, y: float) -> None:
    r = 16
    _pen(draw, (x - r, y), (x + r, y), width=3)
    _pen(draw, (x, y - r), (x, y + r), width=3)
    draw.ellipse((x - 9, y - 9, x + 9, y + 9), outline=_INK, width=2)


def _draw_component(draw: ImageDraw.ImageDraw, comp: Component, at) -> None:
    points = [at(x, y) for x, y in _world_points(comp)]
    draw.polygon(points, fill=_FILL)
    if comp.kind == "rhs":
        t = float(comp.params["t"])
        hole = [
            at(comp.x + t, comp.y + t),
            at(comp.right - t, comp.y + t),
            at(comp.right - t, comp.top - t),
            at(comp.x + t, comp.top - t),
        ]
        draw.polygon(hole, fill=_PAPER)
        _outline_path(draw, hole)
    _outline_path(draw, points)


def _outline_path(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]]) -> None:
    closed = points + points[:1]
    for start, end in zip(closed, closed[1:]):
        _pen(draw, start, end, width=3)


def _mark(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, font: ImageFont.ImageFont) -> None:
    r = 20
    draw.ellipse((x - r, y - r, x + r, y + r), fill=_PAPER, outline=_INK, width=2)
    _ink(draw, (x, y), text, font=font, fill=_INK, anchor="mm")


# ---------- טבלת הנתונים ----------

def _col_centers() -> list[float]:
    centers = []
    x = _TABLE_X
    for width in _COL_WIDTHS:
        centers.append(x + width / 2.0)
        x += width
    return centers


def _draw_table(draw: ImageDraw.ImageDraw, solution: CogSolution, fonts: dict) -> float:
    headers = (
        "i",
        "A [cm²]",
        "Cx [cm]",
        "Cy [cm]",
        "A·Cx [cm³]",
        "A·Cy [cm³]",
        "Ix [cm⁴]",
        "Iy [cm⁴]",
        "|dx| [cm]",
        "|dy| [cm]",
    )
    centers = _col_centers()
    table_right = _TABLE_X + sum(_COL_WIDTHS)

    y = _TABLE_Y + _ROW_H / 2.0
    for center, title in zip(centers, headers):
        _ink(draw, (center, y), title, font=fonts["head"], fill=_INK, anchor="mm")
    header_line_y = _TABLE_Y + _ROW_H
    _pen(draw, (_TABLE_X, header_line_y), (table_right, header_line_y), width=3)

    y = header_line_y
    for row in solution.rows:
        cells = (
            str(row.index),
            _fmt(row.area),
            _fmt(row.cx),
            _fmt(row.cy),
            _fmt(row.a_cx),
            _fmt(row.a_cy),
            _fmt(row.ix),
            _fmt(row.iy),
            _fmt(row.dx),
            _fmt(row.dy),
        )
        for center, cell in zip(centers, cells):
            _ink(draw, (center, y + _ROW_H / 2.0), cell, font=fonts["cell"], fill=_INK, anchor="mm")
        y += _ROW_H

    _pen(draw, (_TABLE_X, y), (table_right, y), width=3)
    sums = (
        "Σ",
        _fmt(solution.sum_area),
        "",
        "",
        _fmt(solution.sum_a_cx),
        _fmt(solution.sum_a_cy),
    )
    for center, cell in zip(centers, sums):
        if cell:
            _ink(draw, (center, y + _ROW_H / 2.0), cell, font=fonts["cell"], fill=_INK, anchor="mm")
    bottom = y + _ROW_H
    _pen(draw, (_TABLE_X, bottom), (table_right, bottom), width=3)

    divider_x = _TABLE_X + _COL_WIDTHS[0]
    _pen(draw, (divider_x, _TABLE_Y), (divider_x, bottom), width=3)
    return bottom


# ---------- נוסחאות ----------

def _fraction(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    numerator: str,
    denominator: str,
    font: ImageFont.ImageFont,
) -> float:
    """שבר מאונך סביב גובה y. מחזיר את הרוחב שנוצל."""
    num_w = _text_w(draw, numerator, font)
    den_w = _text_w(draw, denominator, font)
    width = max(num_w, den_w) + 24
    center = x + width / 2.0
    _ink(draw, (center, y - 42), numerator, font=font, fill=_INK, anchor="mm")
    _ink(draw, (center, y + 42), denominator, font=font, fill=_INK, anchor="mm")
    _pen(draw, (x, y), (x + width, y), width=3)
    return width


def _draw_centroid_formulas(
    draw: ImageDraw.ImageDraw, solution: CogSolution, fonts: dict
) -> None:
    font = fonts["math"]
    blocks = (
        (_CX_BAR_Y, "Cx", "ΣA·Cx", _fmt(solution.sum_a_cx), solution.cx),
        (_CY_BAR_Y, "Cy", "ΣA·Cy", _fmt(solution.sum_a_cy), solution.cy),
    )
    sum_area = _fmt(solution.sum_area)
    for y, name, symbolic, moment, value in blocks:
        x = _FORMULA_X
        label = f"{name} ="
        _ink(draw, (x, y), label, font=font, fill=_INK, anchor="lm")
        x += _text_w(draw, label, font) + 30
        x += _fraction(draw, x, y, symbolic, "ΣA", font) + 30
        _ink(draw, (x, y), "=", font=font, fill=_INK, anchor="lm")
        x += _text_w(draw, "=", font) + 30
        x += _fraction(draw, x, y, moment, sum_area, font) + 30
        _ink(draw, (x, y), "=", font=font, fill=_INK, anchor="lm")
        x += _text_w(draw, "=", font) + 30
        _boxed(draw, x, y, f"{name} = {_fmt(value)} cm", font)


def _steiner_term(inertia: float, area: float, arm: float) -> str:
    return f"({_plain(inertia)} + {_plain(area)}·{_plain(arm)}²)"


def _plain(value: float) -> str:
    """מספר בלי מפריד אלפים — שורות ההצבה של האינרציה ארוכות."""
    return _fmt(value).replace(",", "")


def _draw_inertia_formulas(
    draw: ImageDraw.ImageDraw, solution: CogSolution, fonts: dict
) -> None:
    """שטיינר: Ixx = Σ(Ix + A·dy²) ו-Iyy = Σ(Iy + A·dx²) סביב הצירים המרכזיים."""
    font = fonts["math"]
    blocks = (
        (
            _IXX_TOP_Y,
            "Ixx",
            "Σ(Ix + A·dy²)",
            [_steiner_term(row.ix, row.area, row.dy) for row in solution.rows],
            solution.i_xx,
        ),
        (
            _IYY_TOP_Y,
            "Iyy",
            "Σ(Iy + A·dx²)",
            [_steiner_term(row.iy, row.area, row.dx) for row in solution.rows],
            solution.i_yy,
        ),
    )
    for y, name, symbolic, terms, value in blocks:
        _ink(draw, (_FORMULA_X, y), f"{name} = {symbolic} =", font=font, fill=_INK, anchor="lm")

        substitution = " + ".join(terms)
        x = _FORMULA_X + _INERTIA_INDENT
        sub_font = _fit_font(draw, substitution, _FORMULA_MAX_X - x, font)
        _ink(draw, (x, y + _INERTIA_LINE_H), substitution, font=sub_font, fill=_INK, anchor="lm")

        result_y = y + 2 * _INERTIA_LINE_H
        _ink(draw, (x, result_y), "=", font=font, fill=_INK, anchor="lm")
        _boxed(
            draw,
            x + _text_w(draw, "=", font) + 30,
            result_y,
            f"{name} = {_fmt(value)} cm⁴",
            font,
        )


def _boxed(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, font: ImageFont.ImageFont) -> None:
    width = _text_w(draw, text, font)
    pad_x, pad_y = 14, 16
    left, right = x - pad_x, x + width + pad_x
    top, bottom = y - pad_y - 6, y + pad_y + 6
    _pen(draw, (left, top), (right, top), width=2)
    _pen(draw, (right, top), (right, bottom), width=2)
    _pen(draw, (right, bottom), (left, bottom), width=2)
    _pen(draw, (left, bottom), (left, top), width=2)
    _ink(draw, (x, y), text, font=font, fill=_INK, anchor="lm")
