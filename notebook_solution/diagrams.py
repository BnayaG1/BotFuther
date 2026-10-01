# -*- coding: utf-8 -*-
"""דיאגרמות N/Q/M מתחת לקורה — כתב יד, מקבילות לאורך הקורה."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

import core.statics_calculator as solver
from notebook_solution.page import _CELL_PX, page_pixel_size
from notebook_solution.problem import Problem
from notebook_solution.sketch import (
    _BEAM_SPAN,
    _BEAM_X0,
    _BEAM_Y,
    _FONT_FILES,
    _fmt,
)

_GREEN = (24, 128, 56)
_BLUE = (0, 86, 179)
_RED = (217, 48, 37)

def draw_diagrams(
    image: Image.Image,
    extracted: dict,
    solved: dict,
    problem: Problem,
    eq_bottom: float = 0.0,
    *,
    include_details: bool = True,
) -> None:
    del solved
    data = _curves(extracted)
    if data is None:
        return
    xs, normals, shears, moments = data
    draw = ImageDraw.Draw(image)
    fonts = _fonts()
    dim_rows = 2 if len(problem.stations) > 2 else 1
    _, page_h = page_pixel_size()
    top = _BEAM_Y + 112 + dim_rows * 46 + _CELL_PX * 4
    bottom = page_h - _CELL_PX * 3
    block = max(160.0, (bottom - top) / 3.0)
    half = block * 0.42
    axis_n = top + block * 0.5
    axis_q = top + block * 1.5
    axis_m = top + block * 2.5
    _panel(draw, xs, normals, axis_n, _GREEN, "N(x)", "t", fonts, down=False, half=half)
    _panel(draw, xs, shears, axis_q, _BLUE, "Q(x)", "t", fonts, down=False, half=half)
    _panel(draw, xs, moments, axis_m, _RED, "M(x)", "tm", fonts, down=True, half=half)
    if include_details:
        _draw_point_details(draw, xs, normals, shears, moments, problem, fonts, top, eq_bottom)


def draw_normal_diagram(
    image: Image.Image,
    extracted: dict,
    problem: Problem,
) -> None:
    """מצייר רק את דיאגרמת N(x), במיקום שלה בפתרון המלא."""
    data = _curves(extracted)
    if data is None:
        return
    xs, normals, _shears, _moments = data
    draw = ImageDraw.Draw(image)
    fonts = _fonts()
    dim_rows = 2 if len(problem.stations) > 2 else 1
    _, page_h = page_pixel_size()
    top = _BEAM_Y + 112 + dim_rows * 46 + _CELL_PX * 4
    bottom = page_h - _CELL_PX * 3
    block = max(160.0, (bottom - top) / 3.0)
    half = block * 0.42
    axis_n = top + block * 0.5
    _panel(draw, xs, normals, axis_n, _GREEN, "N(x)", "t", fonts, down=False, half=half)


def draw_normal_shear_diagrams(
    image: Image.Image,
    extracted: dict,
    problem: Problem,
) -> None:
    """מצייר את דיאגרמות N(x) ו־Q(x) במיקומן בפתרון המלא."""
    data = _curves(extracted)
    if data is None:
        return
    xs, normals, shears, _moments = data
    draw = ImageDraw.Draw(image)
    fonts = _fonts()
    dim_rows = 2 if len(problem.stations) > 2 else 1
    _, page_h = page_pixel_size()
    top = _BEAM_Y + 112 + dim_rows * 46 + _CELL_PX * 4
    bottom = page_h - _CELL_PX * 3
    block = max(160.0, (bottom - top) / 3.0)
    half = block * 0.42
    axis_n = top + block * 0.5
    axis_q = top + block * 1.5
    _panel(draw, xs, normals, axis_n, _GREEN, "N(x)", "t", fonts, down=False, half=half)
    _panel(draw, xs, shears, axis_q, _BLUE, "Q(x)", "t", fonts, down=False, half=half)


def _curves(extracted: dict) -> tuple[list[float], list[float], list[float], list[float]] | None:
    data = extracted if isinstance(extracted, dict) else {}
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    skip = bool(meta.get("skip_vision_normalize")) or meta.get("source") == "exercise_generator"
    if not skip:
        from bot.vision import finalize_beam_extraction

        data = finalize_beam_extraction(data, merge_nearby_point_loads=False)
    beam = data.get("beam") if isinstance(data.get("beam"), dict) else {}
    try:
        length = float(beam.get("L", 0) or 0)
    except (TypeError, ValueError):
        return None
    if length <= 0:
        return None

    from bot.engineering import ui_loads_to_solver
    from bot.vision import resolve_beam_support_geometry, vision_loads_to_tool_loads

    raw = beam.get("loads") or []
    loads = ui_loads_to_solver(
        vision_loads_to_tool_loads([dict(ld) for ld in raw if isinstance(ld, dict)]),
        in_tons=True,
    )
    mode, ra_pos, rb_pos = resolve_beam_support_geometry(beam)
    xs = _sample_xs(length, loads, float(ra_pos), float(rb_pos))
    if mode == "cantilever":
        result = solver.solve_cantilever_beam(loads, length, wall_pos=float(ra_pos))
        wall = float(result.get("wall_pos", ra_pos))
        rx = float(result.get("R_Ax", 0.0))
        ry = float(result.get("R_Ay", 0.0))
        ma = float(result.get("diagram_fixed_moment", result.get("M_A", 0.0)))
        normals = [solver.normal_force(x, loads, rx, wall) for x in xs]
        shears = [solver.cantilever_shear_force(x, loads, ry, wall_pos=wall) for x in xs]
        moments = [
            solver.cantilever_bending_moment(x, loads, ry, ma, wall_pos=wall) for x in xs
        ]
        return xs, normals, shears, moments

    ra_x, ra_y, _rb_x, rb_y = solver.compute_reactions(loads, length, float(ra_pos), float(rb_pos))
    normals = [solver.normal_force(x, loads, ra_x, float(ra_pos)) for x in xs]
    shears = [solver.shear_force(x, loads, ra_y, rb_y, float(ra_pos), float(rb_pos)) for x in xs]
    moments = [solver.bending_moment(x, loads, ra_y, rb_y, float(ra_pos), float(rb_pos)) for x in xs]
    return xs, normals, shears, moments


def _sample_xs(length: float, loads: list[dict], ra_pos: float, rb_pos: float) -> list[float]:
    crit = {0.0, float(length), float(ra_pos), float(rb_pos)}
    for ld in loads:
        kind = ld.get("type")
        if kind in ("point", "inclined", "moment"):
            crit.add(float(ld.get("x", 0.0) or 0.0))
        elif kind == "distributed":
            crit.add(float(ld.get("x1", 0.0) or 0.0))
            crit.add(float(ld.get("x2", 0.0) or 0.0))
    xs = set()
    for x in crit:
        x = max(0.0, min(length, x))
        xs.add(x)
        if 0.0 < x < length:
            xs.add(max(0.0, x - 1e-4))
            xs.add(min(length, x + 1e-4))
    for i in range(81):
        xs.add(length * i / 80.0)
    return sorted(xs)


def _panel(
    draw: ImageDraw.ImageDraw,
    xs: list[float],
    values: list[float],
    axis_y: float,
    color: tuple[int, int, int],
    title: str,
    unit: str,
    fonts: dict,
    *,
    down: bool,
    half: float,
) -> None:
    x0 = float(_BEAM_X0)
    x1 = float(_BEAM_X0 + _BEAM_SPAN)
    draw.line([(x0, axis_y), (x1, axis_y)], fill=(0, 0, 0), width=1)
    draw.text((x0 - 36, axis_y), title, font=fonts["title"], fill=color, anchor="rm")
    draw.text((x1 + 36, axis_y), unit, font=fonts["title"], fill=color, anchor="lm")
    peak = max((abs(v) for v in values), default=0.0)
    if peak < 1e-9:
        mid = (x0 + x1) / 2
        _empty_mark(draw, mid, axis_y, color)
        return
    scale = half / peak
    sign = 1.0 if down else -1.0
    pts = [
        (x0 + (x / xs[-1]) * (x1 - x0), axis_y + sign * val * scale)
        for x, val in zip(xs, values)
    ]
    if abs(values[0]) >= 1e-9:
        _stroke(draw, [(x0, axis_y), pts[0]], color, 2)
    _stroke(draw, pts, color, 2)
    if abs(values[-1]) >= 1e-9:
        _stroke(draw, [pts[-1], (x1, axis_y)], color, 2)
    _draw_value_labels(draw, xs, values, pts, axis_y, fonts["val"], color)


def _empty_mark(draw: ImageDraw.ImageDraw, x: float, y: float, color: tuple[int, int, int]) -> None:
    """שני קווים אלכסוניים קצרים באמצע — דיאגרמה ריקה."""
    _stroke(draw, [(x - 10, y + 10), (x + 2, y - 10)], color, 2)
    _stroke(draw, [(x - 2, y + 10), (x + 10, y - 10)], color, 2)


def _signed(value: float) -> str:
    if abs(value) < 1e-9:
        return "0"
    return ("−" if value < 0 else "") + _fmt(value)


def _closest(xs: list[float], values: list[float], x: float) -> float:
    idx = min(range(len(xs)), key=lambda i: abs(xs[i] - x))
    return values[idx]


def _sample_at(xs: list[float], values: list[float], x: float) -> float:
    return _closest(xs, values, x)


def _sample_left(xs: list[float], values: list[float], x: float) -> float:
    if x <= xs[0] + 1e-12:
        return values[0]
    return _closest(xs, values, x - 1e-4)


def _detail_line(
    sym: str,
    label: str,
    prev: float | None,
    cur: float,
    unit: str,
    left: float | None = None,
) -> str:
    name = f"{sym}{label}"
    shown = _signed(cur)
    tail = "0" if abs(cur) < 1e-9 else f"{shown} {unit}"
    start = prev
    if left is not None and abs(left - cur) > 1e-6:
        start = left
    if start is None:
        if abs(cur) < 1e-9:
            return f"{name} = 0"
        sign = "+" if cur > 0 else "−"
        return f"{name} = 0 {sign} {_fmt(cur)} = {tail}"
    delta = cur - start
    if abs(delta) < 1e-9:
        return f"{name} = {tail}"
    sign = "+" if delta > 0 else "−"
    return f"{name} = {_signed(start)} {sign} {_fmt(delta)} = {tail}"


def _draw_point_details(
    draw: ImageDraw.ImageDraw,
    xs: list[float],
    normals: list[float],
    shears: list[float],
    moments: list[float],
    problem: Problem,
    fonts: dict,
    top: float,
    eq_bottom: float,
) -> None:
    if not problem.stations:
        return
    page_w, page_h = page_pixel_size()
    left = float(_BEAM_X0 + _BEAM_SPAN + _CELL_PX * 8)
    right = page_w - _CELL_PX * 4
    col_w = (right - left) / 3
    min_y = max(top, eq_bottom + _CELL_PX * 3)
    bottom = page_h - _CELL_PX * 3
    n = len(problem.stations)
    line_h = 36.0
    block_h = line_h + 6 + n * line_h
    low_y = max(min_y, bottom - block_h)
    y0 = max(min_y, (min_y + low_y) / 2 - _CELL_PX * 5)
    avail = max(80.0, bottom - y0 - 40)
    line_h = min(line_h, max(22.0, avail / max(n, 1)))
    n_vals = [_sample_at(xs, normals, x) for x, _ in problem.stations]
    q_vals = [_sample_at(xs, shears, x) for x, _ in problem.stations]
    m_vals = [_sample_at(xs, moments, x) for x, _ in problem.stations]
    n_lefts = [_sample_left(xs, normals, x) for x, _ in problem.stations]
    q_lefts = [_sample_left(xs, shears, x) for x, _ in problem.stations]
    m_lefts = [_sample_left(xs, moments, x) for x, _ in problem.stations]
    _draw_detail_col(draw, left, y0, "Nx", "N", "t", problem.stations, n_vals, _GREEN, fonts, line_h, n_lefts)
    _draw_detail_col(draw, left + col_w, y0, "Qx", "Q", "t", problem.stations, q_vals, _BLUE, fonts, line_h, q_lefts)
    _draw_detail_col(draw, left + 2 * col_w, y0, "Mx", "M", "tm", problem.stations, m_vals, _RED, fonts, line_h, m_lefts)


def _draw_detail_col(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    title: str,
    sym: str,
    unit: str,
    stations: list[tuple[float, str]],
    values: list[float],
    color: tuple[int, int, int],
    fonts: dict,
    line_h: float,
    lefts: list[float] | None = None,
) -> None:
    draw.text((x, y), title, font=fonts["title"], fill=color, anchor="lm")
    box = draw.textbbox((x, y), title, font=fonts["title"])
    draw.line([(x, box[3] + 2), (box[2], box[3] + 2)], fill=color, width=1)
    y += line_h + 6
    prev: float | None = None
    side = lefts or [None] * len(values)
    for (_, label), cur, before in zip(stations, values, side):
        text = _detail_line(sym, label, prev, cur, unit, left=before)
        draw.text((x, y), text, font=fonts["body"], fill=color, anchor="lm")
        y += line_h
        prev = cur


def _change_indices(xs: list[float], values: list[float]) -> list[int]:
    """נקודות שינוי בלי כפילות: התחלת קטע, קפיצה (הערך החדש), שבירה חדה, קיצון, סוף אם שונה."""
    peak = max(abs(v) for v in values)
    if peak < 1e-9:
        return []
    vtol = max(1e-6, 0.025 * peak)
    n = len(values)
    idxs: list[int] = []

    def notable(v: float) -> bool:
        return abs(v) >= 0.02 * peak

    def push(i: int) -> None:
        if not notable(values[i]):
            return
        if idxs and i == idxs[-1]:
            return
        idxs.append(i)

    if notable(values[0]):
        push(0)
    for i in range(1, n):
        dx = xs[i] - xs[i - 1]
        dv = values[i] - values[i - 1]
        if abs(dx) < 1e-6 and abs(dv) > vtol:
            push(i)
            continue
        if i + 1 >= n:
            continue
        dx1 = xs[i] - xs[i - 1]
        dx2 = xs[i + 1] - xs[i]
        if dx1 < 1e-12 or dx2 < 1e-12:
            continue
        s0 = (values[i] - values[i - 1]) / dx1
        s1 = (values[i + 1] - values[i]) / dx2
        rel = abs(s0 - s1) / (abs(s0) + abs(s1) + peak / max(xs[-1], 1e-9))
        tight = dx1 < 5e-4 or dx2 < 5e-4
        if tight and abs(s0 - s1) > 0.15:
            push(i)
            continue
        if rel > 0.45:
            push(i)
            continue
        if (s0 > 1e-9 and s1 < -1e-9) or (s0 < -1e-9 and s1 > 1e-9):
            push(i)
            continue
        left, right = values[i - 1], values[i + 1]
        if (values[i] >= left + vtol and values[i] >= right + vtol) or (
            values[i] <= left - vtol and values[i] <= right - vtol
        ):
            push(i)
    if notable(values[-1]) and (not idxs or abs(values[-1] - values[idxs[-1]]) > vtol):
        push(n - 1)

    kept: list[int] = []
    for i in idxs:
        text = _fmt(values[i])
        drop = False
        for j in kept:
            if abs(xs[i] - xs[j]) < 5e-4 and abs(values[i] - values[j]) <= vtol:
                drop = True
                break
            if _fmt(values[j]) != text:
                continue
            a, b = (j, i) if j < i else (i, j)
            if all(abs(values[k] - values[i]) <= vtol for k in range(a, b + 1)):
                drop = True
                break
        if not drop:
            kept.append(i)
    return kept


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[float, float]:
    box = draw.textbbox((0, 0), text, font=font)
    return float(box[2] - box[0]), float(box[3] - box[1])


def _box(cx: float, cy: float, w: float, h: float, pad: float = 3.0) -> tuple[float, float, float, float]:
    return (cx - w / 2 - pad, cy - h / 2 - pad, cx + w / 2 + pad, cy + h / 2 + pad)


def _boxes_hit(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _dist_to_poly(px: float, py: float, pts: list[tuple[float, float]]) -> float:
    best = 1e9
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        vx, vy = bx - ax, by - ay
        den = vx * vx + vy * vy
        t = 0.0 if den < 1e-12 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / den))
        best = min(best, math.hypot(px - (ax + t * vx), py - (ay + t * vy)))
    return best


def _draw_value_labels(
    draw: ImageDraw.ImageDraw,
    xs: list[float],
    values: list[float],
    pts: list[tuple[float, float]],
    axis_y: float,
    font: ImageFont.ImageFont,
    color: tuple[int, int, int],
) -> None:
    idxs = _change_indices(xs, values)
    placed: list[tuple[float, float, float, float]] = []
    n = len(pts)
    for i in idxs:
        text = _fmt(values[i])
        w, h = _text_size(draw, text, font)
        px, py = pts[i]
        below = py > axis_y + 2
        above = py < axis_y - 2
        out = 1.0 if below else -1.0
        gap = h / 2 + 6
        trials: list[tuple[float, float]] = []
        if i == 0:
            trials.append((px - w / 2 - 4, py))
        if i == n - 1:
            trials.append((px + w / 2 + 4, py))
        for dist in (gap, gap + 20, gap + 38):
            trials.append((px, py + out * dist))
            trials.append((px + 34, py + out * dist))
            trials.append((px - 34, py + out * dist))
        for dist in (gap, gap + 20):
            trials.append((px, py - out * dist))
            trials.append((px + 34, py - out * dist))
            trials.append((px - 34, py - out * dist))
        if above:
            trials.append((px, py - gap))
        if below:
            trials.append((px, py + gap))

        best: tuple[float, float] | None = None
        best_score = -1e9
        for cx, cy in trials:
            box = _box(cx, cy, w, h, pad=10)
            if any(_boxes_hit(box, other) for other in placed):
                continue
            dist = _dist_to_poly(cx, cy, pts)
            if dist < 4:
                continue
            corners = (
                (box[0], box[1]),
                (box[2], box[1]),
                (box[0], box[3]),
                (box[2], box[3]),
                (cx, cy),
            )
            if min(_dist_to_poly(x, y, pts) for x, y in corners) < 2.5:
                continue
            score = -math.hypot(cx - px, cy - py)
            if (below and cy > py) or (above and cy < py):
                score += 6
            if i == 0 and cx < px:
                score += 4
            if i == n - 1 and cx > px:
                score += 4
            if score > best_score:
                best_score = score
                best = (cx, cy)
        if best is None:
            for lift in (gap + 28, gap + 48, gap + 68):
                cy = py + out * lift
                found = False
                for extra in (0, 30, -30, 56, -56, 82, -82):
                    box = _box(px + extra, cy, w, h, pad=10)
                    if not any(_boxes_hit(box, other) for other in placed):
                        best = (px + extra, cy)
                        found = True
                        break
                if found:
                    break
        if best is None:
            continue
        cx, cy = best
        draw.text((cx, cy), text, font=font, fill=color, anchor="mm")
        placed.append(_box(cx, cy, w, h, pad=10))


def _stroke(
    draw: ImageDraw.ImageDraw,
    pts: list[tuple[float, float]],
    color: tuple[int, int, int],
    width: int,
) -> None:
    if len(pts) < 2:
        return
    smooth: list[tuple[float, float]] = [pts[0]]
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 1.5:
            smooth.append(b)
            continue
        nx, ny = -dy / length, dx / length
        steps = max(2, int(length / 36))
        for s in range(1, steps + 1):
            t = s / steps
            wave = math.sin(math.pi * t) * math.sin((a[0] * 0.13 + a[1] * 0.09 + s) * 0.8)
            smooth.append((a[0] + dx * t + nx * 0.28 * wave, a[1] + dy * t + ny * 0.28 * wave))
    draw.line(smooth, fill=color, width=width, joint="curve")


def _fonts() -> dict[str, ImageFont.ImageFont]:
    path = next((item for item in _FONT_FILES if item.is_file()), None)
    if path is None:
        base = ImageFont.load_default()
        return {"title": base, "val": base, "body": base}
    return {
        "title": ImageFont.truetype(str(path), 24),
        "val": ImageFont.truetype(str(path), 20),
        "body": ImageFont.truetype(str(path), 22),
    }
